from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from privatetv.config import SeriesDetectionSettings
from privatetv.media.titles import normalize_title


@dataclass(frozen=True, slots=True)
class SeriesMetadata:
    series_title: str
    season_number: int
    episode_number: int
    episode_title: str | None = None

    @property
    def sort_key(self) -> str:
        return f"{self.series_title.casefold()}|{self.season_number:04d}|{self.episode_number:04d}"


_PLACEHOLDER_PATTERNS = {
    "seriesName": r"(?P<seriesName>[^/]+?)",
    "seasonNo": r"(?P<seasonNo>\d{1,3})",
    "episodeNo": r"(?P<episodeNo>\d{1,4})",
    "episodeTitle": r"(?P<episodeTitle>[^/]+?)",
    "year": r"(?P<year>\d{4})",
}

_AUTO_PATTERNS = (
    # ALF/Staffel 1/03 - Katzenjammer
    r"(?P<seriesName>[^/]+)/(?:(?:Staffel|Season)\s*)?(?P<seasonNo>\d{1,3})/(?:(?:Folge|Episode|E)\s*)?(?P<episodeNo>\d{1,4})(?:[ ._\-]+(?P<episodeTitle>.*))?",
    # ALF/Staffel 1/Folge 03 - Katzenjammer
    r"(?P<seriesName>[^/]+)/(?:Staffel|Season)\s*(?P<seasonNo>\d{1,3})/(?:Folge|Episode)\s*(?P<episodeNo>\d{1,4})(?:[ ._\-]+(?P<episodeTitle>.*))?",
    # ALF/S01E03 - Katzenjammer or ALF/ALF - S01E03 - Katzenjammer
    r"(?:(?P<seriesName>[^/]+)/)?(?:(?P=seriesName)[ ._\-]+)?[Ss](?P<seasonNo>\d{1,3})[Ee](?P<episodeNo>\d{1,4})(?:[ ._\-]+(?P<episodeTitle>.*))?",
    # ALF/ALF - 1x03 - Katzenjammer or ALF - 1x03 - Katzenjammer
    r"(?:(?P<seriesName>[^/]+)/)?(?:(?P=seriesName)[ ._\-]+)?(?P<seasonNo>\d{1,3})x(?P<episodeNo>\d{1,4})(?:[ ._\-]+(?P<episodeTitle>.*))?",
    # ALF.S01E03.Katzenjammer
    r"(?P<seriesName>.+?)[ ._\-]+[Ss](?P<seasonNo>\d{1,3})[Ee](?P<episodeNo>\d{1,4})(?:[ ._\-]+(?P<episodeTitle>.*))?",
    # ALF - 1x03 - Katzenjammer
    r"(?P<seriesName>.+?)[ ._\-]+(?P<seasonNo>\d{1,3})x(?P<episodeNo>\d{1,4})(?:[ ._\-]+(?P<episodeTitle>.*))?",
)


class SeriesDetector:
    def __init__(self, settings: SeriesDetectionSettings) -> None:
        self._settings = settings
        self._custom_patterns = tuple(
            _compile_custom_pattern(item.pattern) for item in settings.custom_patterns
        )
        self._auto_patterns = tuple(re.compile(pattern, re.IGNORECASE) for pattern in _AUTO_PATTERNS)

    def detect(self, root: Path, path: Path) -> SeriesMetadata | None:
        if not self._settings.enabled:
            return None
        relative = _relative_without_suffix(root, path)

        for pattern in self._custom_patterns:
            metadata = _metadata_from_match(pattern.fullmatch(relative))
            if metadata is not None:
                return metadata

        if not self._settings.auto_patterns:
            return None
        for pattern in self._auto_patterns:
            metadata = _metadata_from_match(pattern.fullmatch(relative))
            if metadata is not None:
                return metadata
            metadata = _metadata_from_match(pattern.fullmatch(Path(relative).name))
            if metadata is not None:
                return metadata
        return None


def _relative_without_suffix(root: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        relative = path.name
    if isinstance(relative, Path):
        relative = relative.with_suffix("")
        return relative.as_posix()
    return Path(str(relative)).with_suffix("").as_posix()


def _compile_custom_pattern(pattern: str) -> re.Pattern[str]:
    regex = []
    index = 0
    seen_placeholders: set[str] = set()
    while index < len(pattern):
        matched_placeholder = False
        for placeholder, replacement in _PLACEHOLDER_PATTERNS.items():
            token = "{" + placeholder + "}"
            if pattern.startswith(token, index):
                if placeholder in seen_placeholders:
                    if placeholder in {"seasonNo", "episodeNo"}:
                        regex.append(f"0*(?P={placeholder})")
                    else:
                        regex.append(f"(?P={placeholder})")
                else:
                    regex.append(replacement)
                    seen_placeholders.add(placeholder)
                index += len(token)
                matched_placeholder = True
                break
        if matched_placeholder:
            continue
        char = pattern[index]
        if char == "*":
            regex.append(".*")
        else:
            regex.append(re.escape(char))
        index += 1
    return re.compile("".join(regex), re.IGNORECASE)


def _metadata_from_match(match: re.Match[str] | None) -> SeriesMetadata | None:
    if match is None:
        return None
    data = match.groupdict()
    series = _clean_text(data.get("seriesName"))
    episode_title = _clean_text(data.get("episodeTitle"))
    season_text = data.get("seasonNo")
    episode_text = data.get("episodeNo")
    if not series or not season_text or not episode_text:
        return None
    try:
        season = int(season_text)
        episode = int(episode_text)
    except ValueError:
        return None
    if season < 0 or episode < 1:
        return None
    return SeriesMetadata(
        series_title=series,
        season_number=season,
        episode_number=episode,
        episode_title=episode_title,
    )


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = normalize_title(value)
    text = re.sub(r"\b(?:720p|1080p|2160p|x264|x265|h264|h265|web[- ]?dl|bluray|dvdrip)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -_")
    return text or None
