from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from hashlib import sha1
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from privatetv.config import AppSettings
from privatetv.domain.models import MediaAsset, MediaItem, ScanStatus, SourceKind
from privatetv.media.local_file_scanner import _contains_surrogate
from privatetv.media.titles import title_from_path
from privatetv.media.probe import FfprobeMediaProbe, ProbeError, ProbeResult
from privatetv.media.dvd_ifo import DvdIfoPgcCandidate, parse_dvd_ifo_main_title_candidates, parse_dvd_ifo_pgc_candidates

LOGGER = logging.getLogger(__name__)

_VOB_RE = re.compile(r"^VTS_(?P<title_set>\d{2})_(?P<part>\d)\.VOB$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DvdTitleSet:
    title_set: str
    files: tuple[Path, ...]
    total_size_bytes: int
    total_duration_seconds: float = 0.0
    duration_source: str = "probe"


class DvdStructureScanner:
    """Find DVD structures and import main title plus short extras."""

    def __init__(self, settings: AppSettings, probe: FfprobeMediaProbe) -> None:
        self._settings = settings
        self._probe = probe

    def scan(self) -> list[tuple[MediaItem, tuple[MediaAsset, ...]]]:
        return list(self.iter_scan_results())

    def iter_scan_results(
        self,
        progress: Callable[[str, Path], None] | None = None,
    ) -> Iterator[tuple[MediaItem, tuple[MediaAsset, ...]]]:
        if not self._settings.media.dvd.enabled or not self._settings.media.dvd.detect_video_ts:
            return

        seen_video_ts: set[Path] = set()
        for root in self._settings.media.directories:
            if not root.exists() or not root.is_dir():
                continue
            for video_ts_dir in self._iter_video_ts_directories(root):
                resolved = video_ts_dir.resolve()
                if resolved in seen_video_ts:
                    continue
                seen_video_ts.add(resolved)
                if _contains_surrogate(resolved):
                    if progress is not None:
                        progress("skip-invalid-path", resolved)
                    continue
                if progress is not None:
                    progress("dvd-structure", resolved)
                for item in self._items_for_video_ts(root, video_ts_dir):
                    yield item

    def _iter_video_ts_directories(self, root: Path):
        if self._is_dvd_structure_directory(root):
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
            if self._is_dvd_structure_directory(child):
                yield child
                continue
            yield from self._walk_recursive(child)

    def _should_skip_directory(self, path: Path) -> bool:
        if self._settings.media.ignore_hidden_directories and path.name.startswith("."):
            return True
        if path.is_symlink() and not self._settings.media.follow_symlinks:
            return True
        return False

    def _is_dvd_structure_directory(self, path: Path) -> bool:
        """Return true for normal VIDEO_TS directories and for loose DVD rip directories.

        Some DVD rips are stored as ``Movie/VIDEO_TS/VTS_01_1.VOB`` while others
        are stored directly as ``Movie/VTS_01_1.VOB`` next to the IFO files.
        Both forms represent one logical DVD title and must be handled by the
        DVD scanner, not as independent local movies.
        """

        if not path.is_dir():
            return False
        if path.name.upper() == "VIDEO_TS":
            if (path / "VIDEO_TS.IFO").exists():
                return True
            return any(_VOB_RE.match(child.name) for child in path.iterdir() if child.is_file())
        has_standard_vob = any(_VOB_RE.match(child.name) for child in path.iterdir() if child.is_file())
        if not has_standard_vob:
            return False
        return (path / "VIDEO_TS.IFO").exists() or any(
            child.name.upper().startswith("VTS_") and child.suffix.upper() == ".IFO"
            for child in path.iterdir()
            if child.is_file()
        )

    def _items_for_video_ts(
        self, root: Path, video_ts_dir: Path
    ) -> Iterator[tuple[MediaItem, tuple[MediaAsset, ...]]]:
        resolved_root = root.resolve()
        resolved_video_ts_dir = video_ts_dir.resolve()
        grouped_title_sets = self._group_title_sets(resolved_video_ts_dir)
        if not grouped_title_sets:
            return

        main_title_set = self._select_main_title_set(resolved_video_ts_dir, grouped_title_sets)
        if main_title_set is None:
            return

        main_item = self._media_item_for_title_set(
            resolved_root=resolved_root,
            resolved_video_ts_dir=resolved_video_ts_dir,
            title_set=main_title_set,
            media_type="dvd_main_title",
            source_uri="dvd://" + resolved_video_ts_dir.as_posix(),
            title=_title_from_video_ts(resolved_video_ts_dir),
            asset_role="dvd_main_title_part",
        )
        if main_item is not None:
            yield main_item

        for extra_title_set in self._select_extra_title_sets(
            resolved_video_ts_dir, grouped_title_sets, main_title_set
        ):
            extra_item = self._media_item_for_title_set(
                resolved_root=resolved_root,
                resolved_video_ts_dir=resolved_video_ts_dir,
                title_set=extra_title_set,
                media_type="dvd_extra_filler",
                source_uri=f"dvd://{resolved_video_ts_dir.as_posix()}#extra-vts-{extra_title_set.title_set}",
                title=f"{_title_from_video_ts(resolved_video_ts_dir)} – DVD Extra {extra_title_set.title_set}",
                asset_role="dvd_extra_part",
            )
            if extra_item is not None:
                yield extra_item

        for pgc_extra in self._select_pgc_extra_candidates(
            resolved_video_ts_dir, grouped_title_sets, main_title_set
        ):
            pgc_item = self._media_item_for_pgc_extra(
                resolved_root=resolved_root,
                resolved_video_ts_dir=resolved_video_ts_dir,
                candidate=pgc_extra,
                files=grouped_title_sets.get(pgc_extra.title_set, ()),
            )
            if pgc_item is not None:
                yield pgc_item

    def _media_item_for_title_set(
        self,
        *,
        resolved_root: Path,
        resolved_video_ts_dir: Path,
        title_set: DvdTitleSet,
        media_type: str,
        source_uri: str,
        title: str,
        asset_role: str,
    ) -> tuple[MediaItem, tuple[MediaAsset, ...]] | None:
        probe_results: list[ProbeResult] = []
        probe_errors: list[str] = []
        for path in title_set.files:
            try:
                probe_results.append(self._probe.probe(path))
            except ProbeError as exc:
                probe_errors.append(str(exc))

        probed_duration_seconds = sum(result.duration_seconds for result in probe_results)
        duration_seconds = title_set.total_duration_seconds or probed_duration_seconds
        if media_type == "dvd_main_title":
            min_duration = self._settings.media.dvd.min_main_title_duration_seconds
            if duration_seconds and duration_seconds < min_duration:
                return None
        else:
            if not _is_dvd_extra_filler_duration(duration_seconds):
                return None

        item = MediaItem(
            id=None,
            source_kind=SourceKind.DVD_STRUCTURE,
            source_uri=source_uri,
            source_root=resolved_root,
            title=title,
            media_type=media_type,
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
                role=asset_role,
                file_size_bytes=path.stat().st_size,
            )
            for index, path in enumerate(title_set.files, start=1)
        )
        return item, assets

    def _group_title_sets(self, video_ts_dir: Path) -> dict[str, tuple[Path, ...]]:
        grouped: dict[str, list[tuple[int, Path]]] = {}
        for child in video_ts_dir.iterdir():
            if not child.is_file():
                continue
            match = _VOB_RE.match(child.name)
            if match is None:
                continue
            part = int(match.group("part"))
            # VTS_xx_0.VOB normally contains menu/navigation material, not movie/bonus content.
            if part == 0:
                continue
            grouped.setdefault(match.group("title_set"), []).append((part, child))
        return {
            title_set: tuple(path for _part, path in sorted(numbered_files, key=lambda item: item[0]))
            for title_set, numbered_files in grouped.items()
        }

    def _select_main_title_set(
        self, video_ts_dir: Path, grouped: dict[str, tuple[Path, ...]]
    ) -> DvdTitleSet | None:
        candidates: list[DvdTitleSet] = []
        min_size_bytes = self._settings.media.dvd.min_main_title_size_mb * 1024 * 1024
        min_duration = self._settings.media.dvd.min_main_title_duration_seconds

        ifo_durations = {
            candidate.title_set: candidate.duration_seconds
            for candidate in parse_dvd_ifo_main_title_candidates(video_ts_dir)
            if candidate.duration_seconds > 0
        }

        for title_set, files in grouped.items():
            total_size = sum(path.stat().st_size for path in files)
            if total_size < min_size_bytes:
                continue
            ifo_duration = ifo_durations.get(title_set, 0.0)
            if ifo_duration > 0:
                duration = ifo_duration
                source = "ifo-pgc"
            else:
                duration = self._probe_title_set_duration(files)
                source = "probe"
            if duration > 0 and duration < min_duration:
                continue
            candidates.append(DvdTitleSet(title_set, files, total_size, duration, source))

        if not candidates:
            return None
        # Prefer the DVD navigation table's longest PGC because this is how a
        # player knows the actual programme chain.  If IFO metadata is missing
        # or broken, fall back to probed duration and finally total VOB size.
        return max(
            candidates,
            key=lambda candidate: (
                candidate.duration_source == "ifo-pgc",
                candidate.total_duration_seconds > 0,
                candidate.total_duration_seconds,
                candidate.total_size_bytes,
            ),
        )

    def _select_extra_title_sets(
        self, video_ts_dir: Path, grouped: dict[str, tuple[Path, ...]], main_title_set: DvdTitleSet
    ) -> tuple[DvdTitleSet, ...]:
        """Return conservative DVD bonus/title-set filler candidates.

        PrivateTV cannot yet address arbitrary PGC/cell chains inside a VTS as
        independent streams, so extras are imported at VTS-title-set granularity.
        This still covers the common DVD-authoring pattern where trailers, short
        bonus clips and logos live in small non-main VTS groups.
        """

        ifo_durations = {
            candidate.title_set: candidate.duration_seconds
            for candidate in parse_dvd_ifo_main_title_candidates(video_ts_dir)
            if candidate.duration_seconds > 0
        }
        extras: list[DvdTitleSet] = []
        for title_set, files in grouped.items():
            if title_set == main_title_set.title_set:
                continue
            total_size = sum(path.stat().st_size for path in files)
            ifo_duration = ifo_durations.get(title_set, 0.0)
            if ifo_duration > 0:
                duration = ifo_duration
                source = "ifo-pgc"
            else:
                duration = self._probe_title_set_duration(files)
                source = "probe"
            if not _is_dvd_extra_filler_duration(duration):
                continue
            extras.append(DvdTitleSet(title_set, files, total_size, duration, source))
        return tuple(sorted(extras, key=lambda candidate: candidate.title_set))

    def _select_pgc_extra_candidates(
        self, video_ts_dir: Path, grouped: dict[str, tuple[Path, ...]], main_title_set: DvdTitleSet
    ) -> tuple[DvdIfoPgcCandidate, ...]:
        """Return short non-main PGCs that can be extracted into real filler clips."""

        candidates = [
            candidate
            for candidate in parse_dvd_ifo_pgc_candidates(video_ts_dir)
            if candidate.title_set in grouped
            and candidate.first_sector is not None
            and candidate.last_sector is not None
            and _is_dvd_extra_filler_duration(candidate.duration_seconds)
        ]
        if not candidates:
            return ()

        # Exclude the chosen main programme chain.  Usually this is the longest
        # PGC in the chosen title set, but authored DVDs may have multiple short
        # PGCs beside it in the same VTS; those remain valid filler candidates.
        main_title_set_candidates = [c for c in candidates if c.title_set == main_title_set.title_set]
        all_pgc_candidates = tuple(parse_dvd_ifo_pgc_candidates(video_ts_dir))
        main_pgc = max(
            (candidate for candidate in all_pgc_candidates if candidate.title_set == main_title_set.title_set),
            key=lambda candidate: candidate.duration_seconds,
            default=None,
        )
        result: list[DvdIfoPgcCandidate] = []
        for candidate in candidates:
            if (
                main_pgc is not None
                and candidate.title_set == main_pgc.title_set
                and candidate.pgc_number == main_pgc.pgc_number
            ):
                continue
            # Avoid duplicating VTS-level extras already imported by patch 37.
            # For non-main VTS sets with exactly one short PGC, the whole VTS
            # item is good enough and does not need an extracted duplicate.
            if candidate.title_set != main_title_set.title_set:
                same_vts = [c for c in all_pgc_candidates if c.title_set == candidate.title_set]
                if len(same_vts) <= 1:
                    continue
            result.append(candidate)
        return tuple(sorted(result, key=lambda candidate: (candidate.title_set, candidate.pgc_number)))

    def _media_item_for_pgc_extra(
        self,
        *,
        resolved_root: Path,
        resolved_video_ts_dir: Path,
        candidate: DvdIfoPgcCandidate,
        files: tuple[Path, ...],
    ) -> tuple[MediaItem, tuple[MediaAsset, ...]] | None:
        if not files or candidate.first_sector is None or candidate.last_sector is None:
            return None
        output_path = self._generated_pgc_extra_path(resolved_video_ts_dir, candidate)
        if not output_path.exists():
            if not self._extract_pgc_extra_clip(files, candidate, output_path):
                return None
        try:
            probe_result = self._probe.probe(output_path)
            # The source of truth is the IFO PGC play time.  FFprobe may report
            # slightly shorter values for tiny/generated fixtures or for clips
            # with incomplete trailing GOPs.
            duration_seconds = candidate.duration_seconds
        except ProbeError as exc:
            LOGGER.warning("Generated DVD PGC extra could not be probed at %s: %s", output_path, exc)
            duration_seconds = candidate.duration_seconds
            probe_result = None
        if not _is_dvd_extra_filler_duration(duration_seconds):
            return None

        dvd_title = _title_from_video_ts(resolved_video_ts_dir)
        source_uri = (
            f"generated://dvd-extra/{_safe_generated_name(resolved_video_ts_dir)}"
            f"/vts-{candidate.title_set}-pgc-{candidate.pgc_number:03d}"
        )
        item = MediaItem(
            id=None,
            source_kind=SourceKind.GENERATED,
            source_uri=source_uri,
            source_root=output_path,
            title=f"{dvd_title} – DVD Extra {candidate.title_set}/{candidate.pgc_number}",
            media_type="dvd_pgc_extra_filler",
            duration_seconds=duration_seconds,
            container=probe_result.container if probe_result is not None else "mp4",
            video_codec=probe_result.video_codec if probe_result is not None else "h264",
            audio_codec=probe_result.audio_codec if probe_result is not None else "aac",
            file_size_bytes=output_path.stat().st_size if output_path.exists() else None,
            mtime=int(output_path.stat().st_mtime) if output_path.exists() else None,
            enabled=True,
            scan_status=ScanStatus.OK,
        )
        asset = MediaAsset(
            id=None,
            media_item_id=0,
            asset_order=1,
            path=output_path,
            role="dvd_pgc_extra_clip",
            file_size_bytes=output_path.stat().st_size if output_path.exists() else None,
        )
        return item, (asset,)

    def _generated_pgc_extra_path(self, video_ts_dir: Path, candidate: DvdIfoPgcCandidate) -> Path:
        base_dir = self._settings.database.path.parent / "generated" / "dvd-extras"
        key = sha1(
            f"{video_ts_dir.as_posix()}|{candidate.title_set}|{candidate.pgc_number}|{candidate.first_sector}|{candidate.last_sector}".encode(
                "utf-8", "surrogatepass"
            )
        ).hexdigest()[:16]
        return base_dir / f"dvd_extra_{key}_vts{candidate.title_set}_pgc{candidate.pgc_number:03d}.mp4"

    def _extract_pgc_extra_clip(
        self, files: tuple[Path, ...], candidate: DvdIfoPgcCandidate, output_path: Path
    ) -> bool:
        if candidate.first_sector is None or candidate.last_sector is None:
            return False
        ffmpeg = shutil.which(str(self._settings.streaming.ffmpeg_path)) or str(self._settings.streaming.ffmpeg_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="privatetv-dvd-extra-", suffix=".vob", delete=False) as handle:
            temp_path = Path(handle.name)
            try:
                _copy_sector_range_to_handle(files, candidate.first_sector, candidate.last_sector, handle)
            except OSError as exc:
                LOGGER.warning("Could not extract DVD PGC sector range %s-%s: %s", candidate.first_sector, candidate.last_sector, exc)
                temp_path.unlink(missing_ok=True)
                return False
        if temp_path.stat().st_size <= 0:
            temp_path.unlink(missing_ok=True)
            return False

        partial_output = output_path.with_suffix(".tmp.mp4")
        command = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-fflags",
            "+genpts",
            "-i",
            str(temp_path),
            "-t",
            f"{candidate.duration_seconds:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(partial_output),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)
            partial_output.replace(output_path)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            stderr = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
            LOGGER.warning("Could not render DVD PGC extra clip %s: %s", output_path, stderr)
            partial_output.unlink(missing_ok=True)
            return False
        finally:
            temp_path.unlink(missing_ok=True)

    def _probe_title_set_duration(self, files: tuple[Path, ...]) -> float:
        duration = 0.0
        for path in files:
            try:
                duration += self._probe.probe(path).duration_seconds
            except ProbeError:
                continue
        return duration



def _copy_sector_range_to_handle(
    files: tuple[Path, ...], first_sector: int, last_sector: int, handle
) -> None:
    if first_sector < 0 or last_sector < first_sector:
        return
    sector_size = 2048
    current_sector = 0
    remaining_first = first_sector
    remaining_last = last_sector
    for path in files:
        file_size = path.stat().st_size
        file_sector_count = (file_size + sector_size - 1) // sector_size
        file_first = current_sector
        file_last = current_sector + file_sector_count - 1
        current_sector += file_sector_count
        if remaining_last < file_first:
            break
        if remaining_first > file_last:
            continue
        copy_first = max(remaining_first, file_first)
        copy_last = min(remaining_last, file_last)
        byte_offset = (copy_first - file_first) * sector_size
        byte_count = min((copy_last - copy_first + 1) * sector_size, file_size - byte_offset)
        if byte_count <= 0:
            continue
        with path.open("rb") as source:
            source.seek(byte_offset)
            _copy_exact(source, handle, byte_count)


def _copy_exact(source, target, byte_count: int) -> None:
    remaining = byte_count
    while remaining > 0:
        chunk = source.read(min(1024 * 1024, remaining))
        if not chunk:
            break
        target.write(chunk)
        remaining -= len(chunk)


def _safe_generated_name(path: Path) -> str:
    return sha1(path.as_posix().encode("utf-8", "surrogatepass")).hexdigest()[:12]


def _title_from_video_ts(video_ts_dir: Path) -> str:
    dvd_root = video_ts_dir.parent if video_ts_dir.name.upper() == "VIDEO_TS" else video_ts_dir
    return title_from_path(dvd_root)


def _first_present(values) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _is_dvd_extra_filler_duration(duration_seconds: float) -> bool:
    return 15 <= duration_seconds <= 600
