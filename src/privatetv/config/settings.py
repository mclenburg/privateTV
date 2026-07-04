from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from privatetv.domain.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class ServerSettings:
    host: str
    port: int
    public_base_url: str


@dataclass(frozen=True, slots=True)
class ChannelSettings:
    id: str
    name: str
    icon: str = ""
    group_title: str = "Local"
    language: str = "de"


@dataclass(frozen=True, slots=True)
class HazardChannelSettings:
    enabled: bool = False
    id: str = "hazardtv"
    name: str = "Hazard TV"
    icon: str = ""
    group_title: str = "Local"
    language: str = "de"
    random_seed: int | None = None
    avoid_immediate_repeat: bool = True


@dataclass(frozen=True, slots=True)
class DvdSettings:
    enabled: bool = True
    detect_video_ts: bool = True
    main_title_strategy: str = "largest_titleset"
    min_main_title_size_mb: int = 500
    min_main_title_duration_seconds: int = 1200


@dataclass(frozen=True, slots=True)
class MediaSettings:
    directories: tuple[Path, ...]
    recursive: bool = True
    follow_symlinks: bool = False
    ignore_hidden_directories: bool = True
    extensions: tuple[str, ...] = (
        ".avi",
        ".mpg",
        ".mpeg",
        ".mp4",
        ".mkv",
        ".ts",
        ".vob",
    )
    dvd: DvdSettings = field(default_factory=DvdSettings)


@dataclass(frozen=True, slots=True)
class ScheduleSettings:
    days_ahead: int
    minimum_days_ahead: int
    timezone: str
    rebuild_hour: int
    strategy: str
    allow_overflow_across_days: bool = True
    random_seed: int | None = None

    @property
    def zoneinfo(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ConfigurationError(f"Unknown timezone: {self.timezone}") from exc


@dataclass(frozen=True, slots=True)
class StreamingSettings:
    max_parallel_streams: int
    output_container: str
    prefer_stream_copy: bool
    transcode_when_needed: bool
    ffmpeg_path: Path
    ffprobe_path: Path
    accepted_seek_tolerance_seconds: int = 10


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    path: Path


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    level: str = "INFO"


@dataclass(frozen=True, slots=True)
class AppSettings:
    server: ServerSettings
    channel: ChannelSettings
    media: MediaSettings
    schedule: ScheduleSettings
    streaming: StreamingSettings
    database: DatabaseSettings
    logging: LoggingSettings
    hazard_channel: HazardChannelSettings = field(default_factory=HazardChannelSettings)


def load_settings(path: Path) -> AppSettings:
    if not path.exists():
        raise ConfigurationError(f"Config file does not exist: {path}")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return settings_from_mapping(raw)


def settings_from_mapping(raw: dict) -> AppSettings:
    try:
        server = raw["server"]
        channel = raw["channel"]
        media = raw["media"]
        schedule = raw["schedule"]
        streaming = raw["streaming"]
        database = raw["database"]
    except KeyError as exc:
        raise ConfigurationError(f"Missing configuration section: {exc.args[0]}") from exc

    dvd = media.get("dvd", {}) or {}
    hazard = raw.get("hazard_channel", {}) or {}
    extensions = tuple(_normalize_extension(ext) for ext in media.get("extensions", []))
    directories = tuple(Path(item) for item in media.get("directories", []))
    if not directories:
        raise ConfigurationError("media.directories must contain at least one directory")

    settings = AppSettings(
        server=ServerSettings(
            host=str(server.get("host", "127.0.0.1")),
            port=int(server.get("port", 9988)),
            public_base_url=str(server.get("public_base_url", "http://127.0.0.1:9988")).rstrip("/"),
        ),
        channel=ChannelSettings(
            id=str(channel.get("id", "privatetv")),
            name=str(channel.get("name", "PrivateTV")),
            icon=str(channel.get("icon", "")),
            group_title=str(channel.get("group_title", "Local")),
            language=str(channel.get("language", "de")),
        ),
        hazard_channel=HazardChannelSettings(
            enabled=bool(hazard.get("enabled", False)),
            id=str(hazard.get("id", "hazardtv")),
            name=str(hazard.get("name", "Hazard TV")),
            icon=str(hazard.get("icon", "")),
            group_title=str(hazard.get("group_title", channel.get("group_title", "Local"))),
            language=str(hazard.get("language", channel.get("language", "de"))),
            random_seed=hazard.get("random_seed"),
            avoid_immediate_repeat=bool(hazard.get("avoid_immediate_repeat", True)),
        ),
        media=MediaSettings(
            directories=directories,
            recursive=bool(media.get("recursive", True)),
            follow_symlinks=bool(media.get("follow_symlinks", False)),
            ignore_hidden_directories=bool(media.get("ignore_hidden_directories", True)),
            extensions=extensions or (".avi", ".mpg", ".mpeg", ".mp4", ".mkv", ".ts", ".vob"),
            dvd=DvdSettings(
                enabled=bool(dvd.get("enabled", True)),
                detect_video_ts=bool(dvd.get("detect_video_ts", True)),
                main_title_strategy=str(dvd.get("main_title_strategy", "largest_titleset")),
                min_main_title_size_mb=int(dvd.get("min_main_title_size_mb", 500)),
                min_main_title_duration_seconds=int(
                    dvd.get("min_main_title_duration_seconds", 1200)
                ),
            ),
        ),
        schedule=ScheduleSettings(
            days_ahead=int(schedule.get("days_ahead", 5)),
            minimum_days_ahead=int(schedule.get("minimum_days_ahead", 3)),
            timezone=str(schedule.get("timezone", "Europe/Berlin")),
            rebuild_hour=int(schedule.get("rebuild_hour", 3)),
            strategy=str(schedule.get("strategy", "shuffle_no_repeat")),
            allow_overflow_across_days=bool(schedule.get("allow_overflow_across_days", True)),
            random_seed=schedule.get("random_seed"),
        ),
        streaming=StreamingSettings(
            max_parallel_streams=int(streaming.get("max_parallel_streams", 4)),
            output_container=str(streaming.get("output_container", "mpegts")),
            prefer_stream_copy=bool(streaming.get("prefer_stream_copy", True)),
            transcode_when_needed=bool(streaming.get("transcode_when_needed", False)),
            ffmpeg_path=Path(streaming.get("ffmpeg_path", "/usr/bin/ffmpeg")),
            ffprobe_path=Path(streaming.get("ffprobe_path", "/usr/bin/ffprobe")),
            accepted_seek_tolerance_seconds=int(
                streaming.get("accepted_seek_tolerance_seconds", 10)
            ),
        ),
        database=DatabaseSettings(path=Path(database.get("path", "var/lib/privatetv/privatetv.sqlite3"))),
        logging=LoggingSettings(level=str((raw.get("logging") or {}).get("level", "INFO"))),
    )
    _validate_settings(settings)
    return settings


def _normalize_extension(extension: str) -> str:
    extension = extension.strip().lower()
    if not extension:
        raise ConfigurationError("Empty media extension configured")
    return extension if extension.startswith(".") else f".{extension}"


def _validate_settings(settings: AppSettings) -> None:
    if settings.streaming.max_parallel_streams < 1:
        raise ConfigurationError("streaming.max_parallel_streams must be at least 1")
    if settings.schedule.days_ahead < 1:
        raise ConfigurationError("schedule.days_ahead must be at least 1")
    if settings.schedule.minimum_days_ahead < 1:
        raise ConfigurationError("schedule.minimum_days_ahead must be at least 1")
    if settings.schedule.minimum_days_ahead > settings.schedule.days_ahead:
        raise ConfigurationError(
            "schedule.minimum_days_ahead must not be greater than schedule.days_ahead"
        )
    if settings.channel.id == settings.hazard_channel.id and settings.hazard_channel.enabled:
        raise ConfigurationError("hazard_channel.id must differ from channel.id")
    if not 0 <= settings.schedule.rebuild_hour <= 23:
        raise ConfigurationError("schedule.rebuild_hour must be between 0 and 23")
    if not 1 <= settings.server.port <= 65535:
        raise ConfigurationError("server.port must be between 1 and 65535")
    parsed_base_url = urlparse(settings.server.public_base_url)
    if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
        raise ConfigurationError("server.public_base_url must be an absolute HTTP(S) URL")
    if not settings.channel.id.strip():
        raise ConfigurationError("channel.id must not be empty")
    if not settings.hazard_channel.id.strip():
        raise ConfigurationError("hazard_channel.id must not be empty")
    if settings.hazard_channel.random_seed is not None and not isinstance(
        settings.hazard_channel.random_seed, int
    ):
        raise ConfigurationError("hazard_channel.random_seed must be an integer or null")
    if settings.streaming.accepted_seek_tolerance_seconds < 0:
        raise ConfigurationError("streaming.accepted_seek_tolerance_seconds must not be negative")
    if not settings.streaming.output_container.strip():
        raise ConfigurationError("streaming.output_container must not be empty")
    _ = settings.schedule.zoneinfo



def settings_to_mapping(settings: AppSettings) -> dict:
    """Convert settings back to a YAML-serializable mapping."""
    return {
        "server": {
            "host": settings.server.host,
            "port": settings.server.port,
            "public_base_url": settings.server.public_base_url,
        },
        "channel": {
            "id": settings.channel.id,
            "name": settings.channel.name,
            "icon": settings.channel.icon,
            "group_title": settings.channel.group_title,
            "language": settings.channel.language,
        },
        "hazard_channel": {
            "enabled": settings.hazard_channel.enabled,
            "id": settings.hazard_channel.id,
            "name": settings.hazard_channel.name,
            "icon": settings.hazard_channel.icon,
            "group_title": settings.hazard_channel.group_title,
            "language": settings.hazard_channel.language,
            "random_seed": settings.hazard_channel.random_seed,
            "avoid_immediate_repeat": settings.hazard_channel.avoid_immediate_repeat,
        },
        "media": {
            "directories": [str(directory) for directory in settings.media.directories],
            "recursive": settings.media.recursive,
            "follow_symlinks": settings.media.follow_symlinks,
            "ignore_hidden_directories": settings.media.ignore_hidden_directories,
            "extensions": list(settings.media.extensions),
            "dvd": {
                "enabled": settings.media.dvd.enabled,
                "detect_video_ts": settings.media.dvd.detect_video_ts,
                "main_title_strategy": settings.media.dvd.main_title_strategy,
                "min_main_title_size_mb": settings.media.dvd.min_main_title_size_mb,
                "min_main_title_duration_seconds": settings.media.dvd.min_main_title_duration_seconds,
            },
        },
        "schedule": {
            "minimum_days_ahead": settings.schedule.minimum_days_ahead,
            "days_ahead": settings.schedule.days_ahead,
            "timezone": settings.schedule.timezone,
            "rebuild_hour": settings.schedule.rebuild_hour,
            "strategy": settings.schedule.strategy,
            "allow_overflow_across_days": settings.schedule.allow_overflow_across_days,
            "random_seed": settings.schedule.random_seed,
        },
        "streaming": {
            "max_parallel_streams": settings.streaming.max_parallel_streams,
            "output_container": settings.streaming.output_container,
            "prefer_stream_copy": settings.streaming.prefer_stream_copy,
            "transcode_when_needed": settings.streaming.transcode_when_needed,
            "ffmpeg_path": str(settings.streaming.ffmpeg_path),
            "ffprobe_path": str(settings.streaming.ffprobe_path),
            "accepted_seek_tolerance_seconds": settings.streaming.accepted_seek_tolerance_seconds,
        },
        "database": {"path": str(settings.database.path)},
        "logging": {"level": settings.logging.level},
    }


def write_settings(path: Path, settings: AppSettings) -> None:
    """Persist settings atomically as YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(settings_to_mapping(settings), handle, sort_keys=False, allow_unicode=True)
    temporary_path.replace(path)
