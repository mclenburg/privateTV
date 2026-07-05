from __future__ import annotations

import re
from pathlib import Path

_DVD_STANDARD_STEM_RE = re.compile(
    r"^(?:VIDEO_TS|VTS_\d{2}_\d|VTS_\d{2}|VTS_\d{2}_\d{1,2})$",
    re.IGNORECASE,
)
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-zäöüß0-9])(?=[A-ZÄÖÜ])")
_LETTER_DIGIT_BOUNDARY_RE = re.compile(r"(?<=[A-Za-zÄÖÜäöüß])(?=\d)|(?<=\d)(?=[A-Za-zÄÖÜäöüß])")
_MULTI_SPACE_RE = re.compile(r"\s+")


def title_from_path(path: Path) -> str:
    """Derive a display title from a media path.

    DVD files often have technical names such as ``VTS_01_2.VOB``.  Those names
    are not useful in an EPG, so for DVD-standard path components the first
    non-standard parent directory is used instead.  The selected name is then
    normalized for human display.
    """

    candidate = _candidate_name(path)
    title = normalize_title(candidate)
    return title or path.name


def normalize_title(value: str) -> str:
    text = value.strip()
    text = text.replace("_", " ").replace(".", " ")
    text = _CAMEL_BOUNDARY_RE.sub(" ", text)
    text = _LETTER_DIGIT_BOUNDARY_RE.sub(" ", text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip()
    return text


def is_dvd_standard_name(name: str) -> bool:
    stem = Path(name).stem
    upper_name = name.upper()
    if upper_name in {"VIDEO_TS", "AUDIO_TS"}:
        return True
    return _DVD_STANDARD_STEM_RE.match(stem) is not None


def _candidate_name(path: Path) -> str:
    if path.suffix:
        leaf = path.stem
    else:
        leaf = path.name
    if not is_dvd_standard_name(path.name):
        return leaf

    for parent in path.parents:
        if not parent.name:
            continue
        if is_dvd_standard_name(parent.name):
            continue
        return parent.name
    return leaf

