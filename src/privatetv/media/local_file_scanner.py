from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from privatetv.config import AppSettings
from privatetv.domain.models import MediaAsset, MediaItem, ScanStatus, SourceKind
from privatetv.media.probe import FfprobeMediaProbe, ProbeError
from privatetv.media.series import SeriesDetector
from privatetv.media.titles import is_dvd_standard_name, title_from_path


@dataclass(frozen=True, slots=True)
class ScanResult:
    scanned_files: int
    imported_items: int
    failed_items: int
    skipped_files: int
    seen_source_uris: frozenset[str]


class LocalFileScanner:
    def __init__(
        self,
        settings: AppSettings,
        probe: FfprobeMediaProbe,
        *,
        directories: tuple[Path, ...] | None = None,
        media_type: str = "video_file",
        progress_kind: str = "local-file",
    ) -> None:
        self._settings = settings
        self._probe = probe
        self._extensions = {extension.lower() for extension in settings.media.extensions}
        self._directories = directories if directories is not None else settings.media.directories
        self._media_type = media_type
        self._progress_kind = progress_kind
        self._series_detector = SeriesDetector(settings.media.series_detection)

    def scan(self) -> list[tuple[MediaItem, tuple[MediaAsset, ...]]]:
        return list(self.iter_scan_results())

    def iter_scan_results(
        self,
        progress: Callable[[str, Path], None] | None = None,
    ) -> Iterator[tuple[MediaItem, tuple[MediaAsset, ...]]]:
        seen_paths: set[Path] = set()
        for root in self._directories:
            if not root.exists() or not root.is_dir():
                continue
            for path in self._iter_video_files(root):
                resolved = path.resolve()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                if _contains_surrogate(resolved):
                    if progress is not None:
                        progress("skip-invalid-path", resolved)
                    continue
                if progress is not None:
                    progress(self._progress_kind, resolved)
                yield self._item_for_file(root, path)

    def _iter_video_files(self, root: Path):
        if self._settings.media.recursive:
            yield from self._walk_recursive(root)
            return
        for child in sorted(root.iterdir(), key=lambda item: str(item).lower()):
            if self._is_supported_file(child):
                yield child

    def _walk_recursive(self, root: Path):
        for child in sorted(root.iterdir(), key=lambda item: str(item).lower()):
            if child.is_dir():
                if self._should_skip_directory(child):
                    continue
                yield from self._walk_recursive(child)
                continue
            if self._is_supported_file(child):
                yield child

    def _should_skip_directory(self, path: Path) -> bool:
        if self._settings.media.ignore_hidden_directories and path.name.startswith("."):
            return True
        if path.is_symlink() and not self._settings.media.follow_symlinks:
            return True
        # VIDEO_TS will be handled by the DVD scanner in patch 3. Avoid importing every VOB as a separate movie.
        if path.name.upper() == "VIDEO_TS" and self._settings.media.dvd.enabled:
            return True
        return False

    def _is_supported_file(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if path.is_symlink() and not self._settings.media.follow_symlinks:
            return False
        if path.suffix.lower() not in self._extensions:
            return False
        # DVD main titles are imported by DvdStructureScanner as one logical item.
        # Only suppress standard VOB fragments inside real DVD structures; loose
        # non-DVD VOB files must remain importable as normal local files.
        if self._settings.media.dvd.enabled and _is_inside_dvd_structure(path):
            return False
        return True

    def _item_for_file(self, root: Path, path: Path) -> tuple[MediaItem, tuple[MediaAsset, ...]]:
        resolved_root = root.resolve()
        resolved_path = path.resolve()
        source_uri = resolved_path.as_uri()
        series_metadata = None
        if self._media_type == "video_file":
            series_metadata = self._series_detector.detect(resolved_root, resolved_path)
        media_type = "episode" if series_metadata is not None else self._media_type
        display_title = title_from_path(resolved_path)
        if series_metadata is not None:
            title_tail = series_metadata.episode_title or display_title
            display_title = (
                f"{series_metadata.series_title} "
                f"S{series_metadata.season_number:02d}E{series_metadata.episode_number:02d}"
            )
            if title_tail:
                display_title = f"{display_title} - {title_tail}"
        try:
            metadata = self._probe.probe(resolved_path)
            item = MediaItem(
                id=None,
                source_kind=SourceKind.LOCAL_FILE,
                source_uri=source_uri,
                source_root=resolved_root,
                title=display_title,
                media_type=media_type,
                duration_seconds=metadata.duration_seconds,
                container=metadata.container,
                video_codec=metadata.video_codec,
                audio_codec=metadata.audio_codec,
                file_size_bytes=metadata.file_size_bytes,
                mtime=metadata.mtime,
                scan_status=ScanStatus.OK,
                series_title=series_metadata.series_title if series_metadata else None,
                season_number=series_metadata.season_number if series_metadata else None,
                episode_number=series_metadata.episode_number if series_metadata else None,
                episode_title=series_metadata.episode_title if series_metadata else None,
                episode_sort_key=series_metadata.sort_key if series_metadata else None,
            )
        except ProbeError as exc:
            file_stat = resolved_path.stat()
            item = MediaItem(
                id=None,
                source_kind=SourceKind.LOCAL_FILE,
                source_uri=source_uri,
                source_root=resolved_root,
                title=display_title,
                media_type=media_type,
                duration_seconds=0.001,
                file_size_bytes=file_stat.st_size,
                mtime=int(file_stat.st_mtime),
                enabled=False,
                scan_status=ScanStatus.PROBE_FAILED,
                scan_error=str(exc),
                series_title=series_metadata.series_title if series_metadata else None,
                season_number=series_metadata.season_number if series_metadata else None,
                episode_number=series_metadata.episode_number if series_metadata else None,
                episode_title=series_metadata.episode_title if series_metadata else None,
                episode_sort_key=series_metadata.sort_key if series_metadata else None,
            )
        asset = MediaAsset(
            id=None,
            media_item_id=0,
            asset_order=1,
            path=resolved_path,
            role="primary",
            file_size_bytes=resolved_path.stat().st_size,
        )
        return item, (asset,)


def _contains_surrogate(path: Path) -> bool:
    return any("\udc80" <= character <= "\udcff" for character in str(path))


def _is_inside_dvd_structure(path: Path) -> bool:
    if not is_dvd_standard_name(path.name):
        return False
    parent = path.parent
    if parent.name.upper() == "VIDEO_TS":
        return True
    if (parent / "VIDEO_TS.IFO").exists():
        return True
    return any(
        child.name.upper().startswith("VTS_") and child.suffix.upper() == ".IFO"
        for child in parent.iterdir()
        if child.is_file()
    )
