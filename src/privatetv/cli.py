from __future__ import annotations

import argparse
import asyncio
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from aiohttp import web

from privatetv import __version__
from privatetv.config import load_settings
from privatetv.db import MediaRepository, ScheduleRepository, connect_database, initialize_database
from privatetv.domain.models import MediaAsset, ScanStatus, SourceKind
from privatetv.http import create_app
from privatetv.media import DvdStructureScanner, FfprobeMediaProbe, LocalFileScanner
from privatetv.schedule import ScheduleMaintainer, resolve_current_programme
from privatetv.tvh import render_empty_xmltv, render_m3u, render_xmltv
from privatetv.util.logging import configure_logging

DEFAULT_CONFIG = Path("config/privatetv.example.yml")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="privatetv", description="PrivateTV local IPTV channel")
    parser.add_argument("--version", action="version", version=f"PrivateTV {__version__}")

    sub = parser.add_subparsers(dest="command")

    for name in (
        "doctor",
        "init-db",
        "scan",
        "list-media",
        "schedule",
        "maintain-schedule",
        "current",
        "serve",
        "m3u",
        "xmltv",
        "status",
    ):
        command = sub.add_parser(name)
        command.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        command.set_defaults(func=globals()[f"cmd_{name.replace('-', '_')}"])

    spike_seek = sub.add_parser("spike-seek")
    spike_seek.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    spike_seek.add_argument("--offset-seconds", type=float, default=120.0)
    spike_seek.set_defaults(func=cmd_spike_seek)

    spike_dvd = sub.add_parser("spike-dvd-concat")
    spike_dvd.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    spike_dvd.add_argument("--offset-seconds", type=float, default=0.0)
    spike_dvd.add_argument("--seconds", type=int, default=15)
    spike_dvd.add_argument("--timeout", type=int, default=30)
    spike_dvd.add_argument("--execute", action="store_true")
    spike_dvd.add_argument("vob", nargs="+", help="VOB files in playback order")
    spike_dvd.set_defaults(func=cmd_spike_dvd_concat)

    spike_tvh = sub.add_parser("spike-tvh-upstream")
    spike_tvh.add_argument("--host", default="127.0.0.1")
    spike_tvh.add_argument("--port", type=int, default=9998)
    spike_tvh.set_defaults(func=cmd_spike_tvh_upstream)

    return parser


def _load(args: argparse.Namespace):
    settings = load_settings(args.config)
    configure_logging(settings.logging.level)
    return settings


def cmd_doctor(args: argparse.Namespace) -> int:
    settings = _load(args)
    checks = [
        ("config", args.config.exists()),
        ("ffmpeg", shutil.which(str(settings.streaming.ffmpeg_path)) is not None or settings.streaming.ffmpeg_path.exists()),
        ("ffprobe", shutil.which(str(settings.streaming.ffprobe_path)) is not None or settings.streaming.ffprobe_path.exists()),
    ]
    for directory in settings.media.directories:
        checks.append((f"media directory: {directory}", directory.exists()))

    failed = False
    for name, ok in checks:
        print(f"{'OK' if ok else 'FAIL'}  {name}")
        failed = failed or not ok
    return 1 if failed else 0


def cmd_init_db(args: argparse.Namespace) -> int:
    settings = _load(args)
    initialize_database(settings.database.path)
    print(f"Initialized database: {settings.database.path}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    settings = _load(args)
    initialize_database(settings.database.path)
    probe = FfprobeMediaProbe(settings.streaming.ffprobe_path)

    source_kinds_to_mark_missing = {SourceKind.LOCAL_FILE, SourceKind.DVD_STRUCTURE}
    seen_by_kind: dict[SourceKind, set[str]] = {kind: set() for kind in source_kinds_to_mark_missing}
    scanned_items = 0
    local_items = 0
    dvd_items = 0
    imported_items = 0
    failed_items = 0
    skipped_items = 0
    upsert_errors: list[str] = []
    progress_counter = 0

    def progress(kind: str, path: Path) -> None:
        nonlocal progress_counter, skipped_items
        progress_counter += 1
        display_path = _safe_path_for_console(path)
        if kind == "skip-invalid-path":
            skipped_items += 1
            print(f"[{progress_counter}] SKIP invalid filename: {display_path}", flush=True)
            return
        print(f"[{progress_counter}] scan {kind}: {display_path}", flush=True)

    local_scanner = LocalFileScanner(settings, probe)
    dvd_scanner = DvdStructureScanner(settings, probe)

    with connect_database(settings.database.path) as connection:
        repository = MediaRepository(connection)
        for item, assets in _chain_scan_results(
            local_scanner.iter_scan_results(progress=progress),
            dvd_scanner.iter_scan_results(progress=progress),
        ):
            scanned_items += 1
            if item.source_kind == SourceKind.LOCAL_FILE:
                local_items += 1
            elif item.source_kind == SourceKind.DVD_STRUCTURE:
                dvd_items += 1

            try:
                repository.upsert_media_item(item, assets)
            except (UnicodeEncodeError, ValueError, OSError, sqlite3.Error) as exc:
                failed_items += 1
                upsert_errors.append(f"{_safe_text(item.source_uri)}: {exc}")
                connection.rollback()
                print(f"  ERROR storing item: {_safe_text(item.source_uri)} ({exc})", flush=True)
                continue

            connection.commit()
            if item.source_kind in seen_by_kind:
                seen_by_kind[item.source_kind].add(item.source_uri)
            if item.scan_status == ScanStatus.OK:
                imported_items += 1
            else:
                failed_items += 1

        missing_items = 0
        for source_kind, seen_source_uris in seen_by_kind.items():
            missing_items += repository.mark_missing_except(source_kind, seen_source_uris)
        refreshed_schedule_titles = ScheduleRepository(connection).refresh_titles_from_media(settings.channel.id)
        connection.commit()

    print(f"Scanned media items: {scanned_items}")
    print(f"Local files:         {local_items}")
    print(f"DVD structures:      {dvd_items}")
    print(f"Imported/updated:    {imported_items}")
    print(f"Probe/store failures:{failed_items}")
    print(f"Skipped files:       {skipped_items}")
    print(f"Marked missing:      {missing_items}")
    print(f"Schedule titles refreshed: {refreshed_schedule_titles}")
    if upsert_errors:
        print("Store errors:")
        for error in upsert_errors[:20]:
            print(f"  - {error}")
        if len(upsert_errors) > 20:
            print(f"  ... {len(upsert_errors) - 20} more")
    return 1 if failed_items else 0



def _chain_scan_results(*iterables):
    for iterable in iterables:
        yield from iterable


def _safe_path_for_console(path: Path) -> str:
    return _safe_text(str(path))


def _safe_text(value: str) -> str:
    return value.encode("utf-8", "backslashreplace").decode("utf-8")


def cmd_list_media(args: argparse.Namespace) -> int:
    settings = _load(args)
    initialize_database(settings.database.path)
    with connect_database(settings.database.path) as connection:
        items = MediaRepository(connection).list_media_items()
    if not items:
        print("No media items found. Run: privatetv scan")
        return 0
    for item in items:
        status = item.scan_status.value
        duration = _format_duration(item.duration_seconds)
        enabled = "enabled" if item.enabled else "disabled"
        print(f"[{item.id}] {item.title} | {duration} | {status} | {enabled} | {item.source_uri}")
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    return _maintain_schedule(args)


def cmd_maintain_schedule(args: argparse.Namespace) -> int:
    return _maintain_schedule(args)


def _maintain_schedule(args: argparse.Namespace) -> int:
    settings = _load(args)
    initialize_database(settings.database.path)
    now = _now(settings)
    with connect_database(settings.database.path) as connection:
        result = ScheduleMaintainer(settings).ensure_schedule(connection, now=now)
    media_count = str(result.schedulable_media_items)
    if result.had_enough_schedule:
        media_count = "not checked; schedule already reaches the minimum horizon"
    print(f"Schedulable media items: {media_count}")
    print(f"Schedule minimum until:  {result.required_until.isoformat()}")
    print(f"Schedule target until:   {result.target_until.isoformat()}")
    print(
        "Schedule before:         "
        f"{result.schedule_until_before.isoformat() if result.schedule_until_before else '-'}"
    )
    print(
        "Schedule after:          "
        f"{result.schedule_until_after.isoformat() if result.schedule_until_after else '-'}"
    )
    print(f"Entries added:           {result.inserted_entries}")
    if result.had_enough_schedule:
        print("No extension needed: stored timeline already reaches the minimum horizon.")
    return 0 if result.schedule_until_after is not None else 1


def cmd_current(args: argparse.Namespace) -> int:
    settings = _load(args)
    initialize_database(settings.database.path)
    now = _now(settings)
    with connect_database(settings.database.path) as connection:
        entries = ScheduleRepository(connection).list_entries_with_media(
            settings.channel.id, start_at=now - timedelta(days=1), end_at=now + timedelta(days=1)
        )
    programme = resolve_current_programme(entries, now=now)
    if programme is None:
        print("No current programme. Run: privatetv schedule")
        return 1
    print(f"Now:     {now.isoformat()}")
    print(f"Title:   {programme.schedule_entry.title}")
    print(f"Start:   {programme.schedule_entry.start_time.isoformat()}")
    print(f"End:     {programme.schedule_entry.end_time.isoformat()}")
    print(f"Offset:  {_format_duration(programme.offset_seconds)}")
    print(f"Source:  {programme.media.source_uri}")
    return 0


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def cmd_serve(args: argparse.Namespace) -> int:
    settings = _load(args)
    app = create_app(settings, config_path=args.config)
    web.run_app(app, host=settings.server.host, port=settings.server.port)
    return 0


def cmd_m3u(args: argparse.Namespace) -> int:
    settings = _load(args)
    print(render_m3u(settings), end="")
    return 0


def cmd_xmltv(args: argparse.Namespace) -> int:
    settings = _load(args)
    initialize_database(settings.database.path)
    now = _now(settings)
    end_at = now + timedelta(days=settings.schedule.days_ahead)
    with connect_database(settings.database.path) as connection:
        ScheduleMaintainer(settings).ensure_schedule(connection, now=now)
        entries = ScheduleRepository(connection).list_entries(settings.channel.id, start_at=now, end_at=end_at)
    print(render_xmltv(settings, entries) if entries else render_empty_xmltv(settings))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    settings = _load(args)
    print(f"PrivateTV {__version__}")
    print(f"Channel: {settings.channel.name} ({settings.channel.id})")
    print(f"Database: {settings.database.path}")
    print(f"Schedule strategy: {settings.schedule.strategy}")
    print(f"Schedule minimum days ahead: {settings.schedule.minimum_days_ahead}")
    print(f"Schedule target days ahead: {settings.schedule.days_ahead}")
    return 0

def _now(settings):
    return datetime.now(settings.schedule.zoneinfo).replace(microsecond=0)



def cmd_spike_seek(args: argparse.Namespace) -> int:
    from privatetv.spikes import build_seek_spike_report

    settings = _load(args)
    print(build_seek_spike_report(settings, offset_seconds=args.offset_seconds).as_text())
    return 0


def cmd_spike_dvd_concat(args: argparse.Namespace) -> int:
    from privatetv.spikes import DvdConcatSpikeRunner

    settings = _load(args)
    paths = [Path(item) for item in args.vob]
    assets = tuple(
        MediaAsset(
            id=None,
            media_item_id=0,
            asset_order=index,
            path=path,
            role="segment",
            file_size_bytes=path.stat().st_size if path.exists() else None,
        )
        for index, path in enumerate(paths, start=1)
    )
    result = DvdConcatSpikeRunner(settings).run(
        assets,
        offset_seconds=args.offset_seconds,
        seconds_to_read=args.seconds,
        timeout_seconds=args.timeout,
        execute=args.execute,
    )
    print(result.as_text())
    return 0


def cmd_spike_tvh_upstream(args: argparse.Namespace) -> int:
    from privatetv.spikes import TvheadendProbeServer

    server = TvheadendProbeServer(host=args.host, port=args.port)
    print("PrivateTV tvheadend upstream probe")
    print("==================================")
    print(f"M3U URL:    http://{args.host}:{args.port}/probe.m3u")
    print(f"Status URL: http://{args.host}:{args.port}/status")
    print("Add the M3U URL as an IPTV automatic network in tvheadend, open the channel")
    print("from multiple clients, then check /status for max_concurrent_connections.")
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("Stopped upstream probe.")
    return 0
