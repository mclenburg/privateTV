from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SECTOR_SIZE = 2048
MAX_PLAUSIBLE_PGC_DURATION_SECONDS = 6 * 60 * 60



@dataclass(frozen=True, slots=True)
class DvdIfoTitleCandidate:
    """Best-effort result extracted from DVD-Video IFO navigation tables."""

    title_set: str
    duration_seconds: float
    source: str


@dataclass(frozen=True, slots=True)
class DvdIfoPgcCandidate:
    """A playable Program Chain candidate from a DVD title set.

    The sector range is expressed in DVD 2048-byte sectors relative to the
    corresponding VTS VOB stream.  It is best-effort metadata for extracting
    short bonus clips from within a title set.
    """

    title_set: str
    pgc_number: int
    duration_seconds: float
    first_sector: int | None = None
    last_sector: int | None = None
    source: str = "ifo-pgc"


def parse_dvd_ifo_main_title_candidates(video_ts_dir: Path) -> tuple[DvdIfoTitleCandidate, ...]:
    """Return likely DVD main-title candidates by reading IFO PGC play times.

    This is intentionally a conservative, dependency-free parser.  It reads the
    DVD-Video navigation tables that are useful for PrivateTV's scanner:

    * ``VIDEO_TS.IFO`` TT_SRPT points to user-visible title sets.
    * ``VTS_XX_0.IFO`` VTS_PGCITI contains Program Chain play times.

    If a table is missing or malformed, the function returns the candidates it
    could extract and lets the caller fall back to VOB probing/size heuristics.
    """

    video_ts_dir = video_ts_dir.resolve()
    visible_title_sets = _read_visible_title_sets(video_ts_dir)
    if visible_title_sets:
        title_sets = sorted(visible_title_sets)
    else:
        title_sets = sorted(_available_vts_numbers(video_ts_dir))

    candidates: list[DvdIfoTitleCandidate] = []
    for title_set in title_sets:
        duration = _read_longest_vts_pgc_duration(video_ts_dir, title_set)
        if duration > 0:
            candidates.append(
                DvdIfoTitleCandidate(
                    title_set=f"{title_set:02d}",
                    duration_seconds=duration,
                    source="ifo-pgc",
                )
            )
    return tuple(candidates)



def parse_dvd_ifo_pgc_candidates(video_ts_dir: Path) -> tuple[DvdIfoPgcCandidate, ...]:
    """Return individual PGC candidates with play time and cell sector ranges.

    This parser intentionally stays dependency-free.  It is not a full DVD VM;
    it only extracts enough from VTS_PGCITI to let the scanner identify short
    bonus clips authored as separate PGCs inside an otherwise shared VTS.  When
    cell playback information is missing, the candidate is still returned with
    a duration but without a sector range, allowing callers to ignore it for
    extraction and keep using the older VTS-level fallback.
    """

    video_ts_dir = video_ts_dir.resolve()
    visible_title_sets = _read_visible_title_sets(video_ts_dir)
    title_sets = sorted(visible_title_sets) if visible_title_sets else sorted(_available_vts_numbers(video_ts_dir))

    candidates: list[DvdIfoPgcCandidate] = []
    for title_set in title_sets:
        candidates.extend(_read_vts_pgc_candidates(video_ts_dir, title_set))
    return tuple(candidates)


def _read_visible_title_sets(video_ts_dir: Path) -> set[int]:
    data = _read_ifo_or_bup(video_ts_dir / "VIDEO_TS.IFO")
    if data is None:
        return set()

    # VMGI_MAT stores the TT_SRPT start sector at byte 0xC4 in big-endian DVD
    # sectors.  Invalid authoring tools occasionally leave this empty; ignore
    # nonsense and fall back to VTS IFO scanning.
    table_offset = _sector_offset_from_u32(data, 0xC4)
    if table_offset is None:
        return set()
    if table_offset + 8 > len(data):
        return set()

    try:
        title_count = int.from_bytes(data[table_offset : table_offset + 2], "big")
    except ValueError:
        return set()
    if title_count <= 0 or title_count > 99:
        return set()

    title_sets: set[int] = set()
    entry_offset = table_offset + 8
    for index in range(title_count):
        offset = entry_offset + index * 12
        if offset + 12 > len(data):
            break
        vts_no = data[offset + 6]
        if 1 <= vts_no <= 99:
            title_sets.add(vts_no)
    return title_sets


def _available_vts_numbers(video_ts_dir: Path) -> set[int]:
    result: set[int] = set()
    for child in video_ts_dir.iterdir():
        name = child.name.upper()
        if not child.is_file():
            continue
        if name.startswith("VTS_") and (name.endswith("_0.IFO") or name.endswith("_0.BUP")):
            try:
                result.add(int(name[4:6]))
            except ValueError:
                continue
    return result


def _read_longest_vts_pgc_duration(video_ts_dir: Path, title_set: int) -> float:
    return max(
        (candidate.duration_seconds for candidate in _read_vts_pgc_candidates(video_ts_dir, title_set)),
        default=0.0,
    )


def _read_vts_pgc_candidates(video_ts_dir: Path, title_set: int) -> list[DvdIfoPgcCandidate]:
    data = _read_ifo_or_bup(video_ts_dir / f"VTS_{title_set:02d}_0.IFO")
    if data is None:
        return []

    # VTSI_MAT stores the VTS_PGCITI start sector at byte 0xCC.
    table_offset = _sector_offset_from_u32(data, 0xCC)
    if table_offset is None or table_offset + 8 > len(data):
        return []

    try:
        pgc_count = int.from_bytes(data[table_offset : table_offset + 2], "big")
    except ValueError:
        return []
    if pgc_count <= 0 or pgc_count > 4096:
        return []

    candidates: list[DvdIfoPgcCandidate] = []
    entry_offset = table_offset + 8
    for index in range(pgc_count):
        offset = entry_offset + index * 8
        if offset + 8 > len(data):
            break
        pgc_start = int.from_bytes(data[offset + 4 : offset + 8], "big")
        pgc_offset = table_offset + pgc_start
        duration = _read_pgc_play_time(data, pgc_offset)
        if duration <= 0:
            continue
        sector_range = _read_pgc_cell_sector_range(data, pgc_offset)
        candidates.append(
            DvdIfoPgcCandidate(
                title_set=f"{title_set:02d}",
                pgc_number=index + 1,
                duration_seconds=duration,
                first_sector=sector_range[0] if sector_range is not None else None,
                last_sector=sector_range[1] if sector_range is not None else None,
            )
        )
    return candidates


def _read_pgc_play_time(data: bytes, pgc_offset: int) -> float:
    if pgc_offset < 0 or pgc_offset + 8 > len(data):
        return 0.0

    # The VTS_PGCITI entry points to a PGC descriptor whose first two bytes are
    # reserved in real authored DVDs encountered by PrivateTV.  The useful PGC
    # header starts after those bytes: program count at +2, cell count at +3,
    # and PGC_PLAY_TIME at +4..+7.  Earlier PrivateTV builds read from +2, which
    # interpreted the program/cell counts as hours/minutes and produced bogus
    # durations such as 04:05:00 or 05:05:00 for children's DVDs that actually
    # contain 00:27:29 or 00:40:50 titles.
    primary_raw = data[pgc_offset + 4 : pgc_offset + 8]
    primary = _decode_dvd_time(primary_raw)
    if primary > 0:
        return primary
    return 0.0



def _read_pgc_cell_sector_range(data: bytes, pgc_offset: int) -> tuple[int, int] | None:
    if pgc_offset < 0 or pgc_offset + 0x16 > len(data):
        return None
    cell_count = data[pgc_offset + 3]
    if cell_count <= 0 or cell_count > 255:
        return None
    cell_playback_offset = int.from_bytes(data[pgc_offset + 0x14 : pgc_offset + 0x16], "big")
    if cell_playback_offset <= 0:
        return None
    table_offset = pgc_offset + cell_playback_offset
    if table_offset < 0 or table_offset + cell_count * 24 > len(data):
        return None

    starts: list[int] = []
    ends: list[int] = []
    for cell_index in range(cell_count):
        offset = table_offset + cell_index * 24
        first_sector = int.from_bytes(data[offset + 8 : offset + 12], "big")
        last_sector = int.from_bytes(data[offset + 20 : offset + 24], "big")
        if last_sector < first_sector:
            continue
        starts.append(first_sector)
        ends.append(last_sector)
    if not starts or not ends:
        return None
    return min(starts), max(ends)


def _decode_dvd_time(raw: bytes) -> float:
    if len(raw) != 4:
        return 0.0
    hours = _bcd_to_int(raw[0])
    minutes = _bcd_to_int(raw[1])
    seconds = _bcd_to_int(raw[2])
    if hours is None or minutes is None or seconds is None:
        return 0.0
    if minutes >= 60 or seconds >= 60:
        return 0.0
    duration = float(hours * 3600 + minutes * 60 + seconds)
    if duration > MAX_PLAUSIBLE_PGC_DURATION_SECONDS:
        return 0.0
    return duration


def _bcd_to_int(value: int) -> int | None:
    high = (value >> 4) & 0x0F
    low = value & 0x0F
    if high > 9 or low > 9:
        return None
    return high * 10 + low


def _sector_offset_from_u32(data: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 4 > len(data):
        return None
    sector = int.from_bytes(data[offset : offset + 4], "big")
    byte_offset = sector * SECTOR_SIZE
    if byte_offset <= 0 or byte_offset >= len(data):
        return None
    return byte_offset


def _read_ifo_or_bup(ifo_path: Path) -> bytes | None:
    for candidate in (ifo_path, ifo_path.with_suffix(".BUP")):
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.read_bytes()
        except OSError:
            continue
    return None
