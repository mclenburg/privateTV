from __future__ import annotations

import argparse
import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from aiohttp import web

from privatetv import __version__
from privatetv.config import load_settings
from privatetv.db import MediaRepository, ScheduleRepository, connect_database, initialize_database
from privatetv.domain.models import MediaAsset, SourceKind
from privatetv.http import create_app
from privatetv.media import DvdStructureScanner, FfprobeMediaProbe, LocalFileScanner, store_scan_results
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
    local_results = LocalFileScanner(settings, probe).scan()
    dvd_results = DvdStructureScanner(settings, probe).scan()
    scan_results = [*local_results, *dvd_results]
    with connect_database(settings.database.path) as connection:
        summary = store_scan_results(
            connection, scan_results, {SourceKind.LOCAL_FILE, SourceKind.DVD_STRUCTURE}
        )
    print(f"Scanned media items: {summary.scanned_items}")
    print(f"Local files:         {len(local_results)}")
    print(f"DVD structures:      {len(dvd_results)}")
    print(f"Imported/updated:    {summary.imported_items}")
    print(f"Probe failures:       {summary.failed_items}")
    print(f"Marked missing:       {summary.missing_items}")
    return 1 if summary.failed_items else 0


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
