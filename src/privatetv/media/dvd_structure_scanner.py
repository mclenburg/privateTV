from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from privatetv.config import AppSettings
from privatetv.domain.models import MediaAsset, MediaItem, ScanStatus, SourceKind
from privatetv.media.local_file_scanner import title_from_path
from privatetv.media.probe import FfprobeMediaProbe, ProbeError, ProbeResult

_VOB_RE = re.compile(r"^VTS_(?P<title_set>\d{2})_(?P<part>\d)\.VOB$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DvdTitleSet:
    title_set: str
    files: tuple[Path, ...]
    total_size_bytes: int


class DvdStructureScanner:
    """Find VIDEO_TS directories and import the largest VOB title set as one movie."""

    def __init__(self, settings: AppSettings, probe: FfprobeMediaProbe) -> None:
        self._settings = settings
        self._probe = probe

    def scan(self) -> list[tuple[MediaItem, tuple[MediaAsset, ...]]]:
        if not self._settings.media.dvd.enabled or not self._settings.media.dvd.detect_video_ts:
            return []

        items: list[tuple[MediaItem, tuple[MediaAsset, ...]]] = []
        seen_video_ts: set[Path] = set()
        for root in self._settings.media.directories:
            if not root.exists() or not root.is_dir():
                continue
            for video_ts_dir in self._iter_video_ts_directories(root):
                resolved = video_ts_dir.resolve()
                if resolved in seen_video_ts:
                    continue
                seen_video_ts.add(resolved)
                item = self._item_for_video_ts(root, video_ts_dir)
                if item is not None:
                    items.append(item)
        return items

    def _iter_video_ts_directories(self, root: Path):
        if self._is_video_ts_directory(root):
            yield root
            return
        if not self._settings.media.recursive:
            return
        yield from self._walk_recursive(root)

    def _walk_recursive(self, directory: Path):
        for child in sorted(directory.iterdir(), key=lambda item: str(item).lower()):
            if not child.is_dir():
                continue
            if self._should_skip_directory(child):
                continue
            if self._is_video_ts_directory(child):
                yield child
                continue
            yield from self._walk_recursive(child)

    def _should_skip_directory(self, path: Path) -> bool:
        if self._settings.media.ignore_hidden_directories and path.name.startswith("."):
            return True
        if path.is_symlink() and not self._settings.media.follow_symlinks:
            return True
        return False

    def _is_video_ts_directory(self, path: Path) -> bool:
        if path.name.upper() != "VIDEO_TS":
            return False
        if (path / "VIDEO_TS.IFO").exists():
            return True
        return any(_VOB_RE.match(child.name) for child in path.iterdir() if child.is_file())

    def _item_for_video_ts(
        self, root: Path, video_ts_dir: Path
    ) -> tuple[MediaItem, tuple[MediaAsset, ...]] | None:
        title_set = self._select_main_title_set(video_ts_dir)
        if title_set is None:
            return None

        probe_results: list[ProbeResult] = []
        probe_errors: list[str] = []
        for path in title_set.files:
            try:
                probe_results.append(self._probe.probe(path))
            except ProbeError as exc:
                probe_errors.append(str(exc))

        duration_seconds = sum(result.duration_seconds for result in probe_results)
        min_duration = self._settings.media.dvd.min_main_title_duration_seconds
        if duration_seconds and duration_seconds < min_duration:
            return None

        source_uri = "dvd://" + video_ts_dir.resolve().as_posix()
        item = MediaItem(
            id=None,
            source_kind=SourceKind.DVD_STRUCTURE,
            source_uri=source_uri,
            source_root=root,
            title=_title_from_video_ts(video_ts_dir),
            media_type="dvd_main_title",
            duration_seconds=duration_seconds if duration_seconds > 0 else 0.001,
            container="dvd-video",
            video_codec=_first_present(result.video_codec for result in probe_results),
            audio_codec=_first_present(result.audio_codec for result in probe_results),
            file_size_bytes=title_set.total_size_bytes,
            mtime=max(int(path.stat().st_mtime) for path in title_set.files),
            enabled=duration_seconds > 0,
            scan_status=ScanStatus.OK if duration_seconds > 0 else ScanStatus.PROBE_FAILED,
            scan_error="; ".join(probe_errors) if probe_errors and duration_seconds <= 0 else None,
        )
        assets = tuple(
            MediaAsset(
                id=None,
                media_item_id=0,
                asset_order=index,
                path=path,
                role="dvd_main_title_part",
                file_size_bytes=path.stat().st_size,
            )
            for index, path in enumerate(title_set.files, start=1)
        )
        return item, assets

    def _select_main_title_set(self, video_ts_dir: Path) -> DvdTitleSet | None:
        grouped: dict[str, list[tuple[int, Path]]] = {}
        for child in video_ts_dir.iterdir():
            if not child.is_file():
                continue
            match = _VOB_RE.match(child.name)
            if match is None:
                continue
            part = int(match.group("part"))
            # VTS_xx_0.VOB normally contains menu/navigation material, not the main movie chain.
            if part == 0:
                continue
            grouped.setdefault(match.group("title_set"), []).append((part, child))

        candidates: list[DvdTitleSet] = []
        min_size_bytes = self._settings.media.dvd.min_main_title_size_mb * 1024 * 1024
        for title_set, numbered_files in grouped.items():
            files = tuple(path for _part, path in sorted(numbered_files, key=lambda item: item[0]))
            total_size = sum(path.stat().st_size for path in files)
            if total_size < min_size_bytes:
                continue
            candidates.append(DvdTitleSet(title_set, files, total_size))

        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate.total_size_bytes)


def _title_from_video_ts(video_ts_dir: Path) -> str:
    dvd_root = video_ts_dir.parent
    return title_from_path(dvd_root)


def _first_present(values) -> str | None:
    for value in values:
        if value:
            return value
    return None
