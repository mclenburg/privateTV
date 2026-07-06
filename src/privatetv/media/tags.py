from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

from privatetv.domain.errors import ConfigurationError
from privatetv.domain.models import MediaItem, SourceKind


@dataclass(frozen=True, slots=True)
class FileTagRule:
    add: tuple[str, ...] = ()
    remove: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TagRules:
    directory_tags: dict[Path, tuple[str, ...]] = field(default_factory=dict)
    file_tags: dict[Path, FileTagRule] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "TagRules":
        return cls()


def load_tag_rules(path: Path | None) -> TagRules:
    if path is None:
        return TagRules.empty()
    if not path.exists():
        raise ConfigurationError(f"media.tag_file does not exist: {path}")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ConfigurationError("Tag file must contain a YAML mapping")
    return TagRules(
        directory_tags=_directory_tags_from_mapping(raw.get("directory_tags", {}) or {}),
        file_tags=_file_tags_from_mapping(raw.get("file_tags", {}) or {}),
    )


def tags_for_media_item(item: MediaItem, rules: TagRules | None = None) -> tuple[str, ...]:
    tags = set(_automatic_tags(item))
    path = _path_for_item(item)
    rules = rules or TagRules.empty()

    if path is not None:
        for directory, directory_tags in rules.directory_tags.items():
            if _is_relative_to(path, directory):
                tags.update(directory_tags)
        file_rule = rules.file_tags.get(path)
        if file_rule is not None:
            tags.update(file_rule.add)
            tags.difference_update(file_rule.remove)

    return tuple(sorted(tag for tag in tags if tag))


def validate_tag_rules(rules: TagRules) -> list[str]:
    warnings: list[str] = []
    for directory in sorted(rules.directory_tags, key=str):
        if not directory.exists():
            warnings.append(f"directory tag path does not exist: {directory}")
    for path in sorted(rules.file_tags, key=str):
        if not path.exists():
            warnings.append(f"file tag path does not exist: {path}")
    return warnings


def _directory_tags_from_mapping(raw: object) -> dict[Path, tuple[str, ...]]:
    if not isinstance(raw, dict):
        raise ConfigurationError("tag file directory_tags must be a mapping")
    result: dict[Path, tuple[str, ...]] = {}
    for key, value in raw.items():
        result[Path(str(key)).resolve()] = _normalize_tags(value, f"directory_tags.{key}")
    return result


def _file_tags_from_mapping(raw: object) -> dict[Path, FileTagRule]:
    if not isinstance(raw, dict):
        raise ConfigurationError("tag file file_tags must be a mapping")
    result: dict[Path, FileTagRule] = {}
    for key, value in raw.items():
        path = Path(str(key)).resolve()
        if isinstance(value, dict):
            add = _normalize_tags(value.get("add", []) or [], f"file_tags.{key}.add")
            remove = _normalize_tags(value.get("remove", []) or [], f"file_tags.{key}.remove")
        else:
            add = _normalize_tags(value, f"file_tags.{key}")
            remove = ()
        result[path] = FileTagRule(add=add, remove=remove)
    return result


def _normalize_tags(raw: object, context: str) -> tuple[str, ...]:
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        raise ConfigurationError(f"{context} must be a tag string or list of tag strings")
    normalized: list[str] = []
    for value in values:
        tag = str(value).strip().lower().replace(" ", "_")
        if not tag:
            continue
        if any(ch in tag for ch in ",;"):
            raise ConfigurationError(f"Invalid tag in {context}: {tag}")
        normalized.append(tag)
    return tuple(dict.fromkeys(normalized))


def _automatic_tags(item: MediaItem) -> tuple[str, ...]:
    tags = {item.media_type.strip().lower()} if item.media_type.strip() else set()
    if item.media_type in {"filler", "trailer", "bumper", "commercial", "advertisement", "dvd_preview"}:
        tags.add("filler")
        if item.duration_seconds <= 60:
            tags.add("short")
    elif item.media_type == "generated_countdown":
        tags.update({"generated", "countdown", "filler"})
    elif item.media_type == "generated_promo":
        tags.update({"generated", "promo", "filler"})
    elif item.source_kind == SourceKind.DVD_STRUCTURE or item.media_type == "dvd_main_title":
        tags.update({"movie", "dvd"})
    else:
        tags.add("movie")
        if item.duration_seconds and item.duration_seconds < 900:
            tags.add("short")
    return tuple(sorted(tags))


def _path_for_item(item: MediaItem) -> Path | None:
    if item.source_kind == SourceKind.GENERATED:
        return item.source_root.resolve() if item.source_root else None
    parsed = urlparse(item.source_uri)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path)).resolve()
    if parsed.scheme == "dvd":
        return Path(unquote(parsed.path)).resolve()
    if item.source_root is not None:
        return item.source_root.resolve()
    return None


def _is_relative_to(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False
