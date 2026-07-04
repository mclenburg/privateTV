from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from privatetv.config import AppSettings
from privatetv.domain.models import MediaAsset, MediaItem, ScanStatus, SourceKind
from privatetv.media.probe import FfprobeMediaProbe, ProbeError


@dataclass(frozen=True, slots=True)
class ScanResult:
    scanned_files: int
    imported_items: int
    failed_items: int
    skipped_files: int
    seen_source_uris: frozenset[str]


class LocalFileScanner:
    def __init__(self, settings: AppSettings, probe: FfprobeMediaProbe) -> None:
        self._settings = settings
        self._probe = probe
        self._extensions = {extension.lower() for extension in settings.media.extensions}

    def scan(self) -> list[tuple[MediaItem, tuple[MediaAsset, ...]]]:
        items: list[tuple[MediaItem, tuple[MediaAsset, ...]]] = []
        seen_paths: set[Path] = set()
        for root in self._settings.media.directories:
            if not root.exists() or not root.is_dir():
                continue
            for path in self._iter_video_files(root):
                resolved = path.resolve()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                items.append(self._item_for_file(root, path))
        return items

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
        return path.suffix.lower() in self._extensions

    def _item_for_file(self, root: Path, path: Path) -> tuple[MediaItem, tuple[MediaAsset, ...]]:
        resolved_root = root.resolve()
        resolved_path = path.resolve()
        source_uri = resolved_path.as_uri()
        try:
            metadata = self._probe.probe(resolved_path)
            item = MediaItem(
                id=None,
                source_kind=SourceKind.LOCAL_FILE,
                source_uri=source_uri,
                source_root=resolved_root,
                title=title_from_path(resolved_path),
                media_type="video_file",
                duration_seconds=metadata.duration_seconds,
                container=metadata.container,
                video_codec=metadata.video_codec,
                audio_codec=metadata.audio_codec,
                file_size_bytes=metadata.file_size_bytes,
                mtime=metadata.mtime,
                scan_status=ScanStatus.OK,
            )
        except ProbeError as exc:
            file_stat = resolved_path.stat()
            item = MediaItem(
                id=None,
                source_kind=SourceKind.LOCAL_FILE,
                source_uri=source_uri,
                source_root=resolved_root,
                title=title_from_path(resolved_path),
                media_type="video_file",
                duration_seconds=0.001,
                file_size_bytes=file_stat.st_size,
                mtime=int(file_stat.st_mtime),
                enabled=False,
                scan_status=ScanStatus.PROBE_FAILED,
                scan_error=str(exc),
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


def title_from_path(path: Path) -> str:
    return path.stem.replace("_", " ").replace(".", " ").strip() or path.name
