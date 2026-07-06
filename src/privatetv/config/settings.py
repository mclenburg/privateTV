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
    tag_file: Path | None = None
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
    random_seed: int | None = None

    @property
    def zoneinfo(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ConfigurationError(f"Unknown timezone: {self.timezone}") from exc




@dataclass(frozen=True, slots=True)
class ProgramBlockAnchorSettings:
    enabled: bool = False
    time: str = "20:15"
    title: str = "Der 20:15 Film"
    allowed_tags: tuple[str, ...] = ()
    denied_tags: tuple[str, ...] = ()
    tag_match: str = "any"


@dataclass(frozen=True, slots=True)
class ProgramBlockSettings:
    enabled: bool = False
    start: str = "06:00"
    duration_seconds: int = 9000
    title: str = "PrivateTV Block"
    allowed_tags: tuple[str, ...] = ()
    denied_tags: tuple[str, ...] = ()
    tag_match: str = "any"
    if_empty: str = "continue_current_mode"


@dataclass(frozen=True, slots=True)
class GeneratedCountdownSettings:
    enabled: bool = False
    max_duration_seconds: int = 60
    title: str = "Gleich geht's weiter"


@dataclass(frozen=True, slots=True)
class GeneratedPromoVariantSettings:
    enabled: bool = False
    title_template: str = "Coming soon"
    include_air_time: bool = False


@dataclass(frozen=True, slots=True)
class GeneratedPromosSettings:
    enabled: bool = False
    duration_min_seconds: int = 15
    duration_max_seconds: int = 30
    next_up: GeneratedPromoVariantSettings = field(
        default_factory=lambda: GeneratedPromoVariantSettings(
            enabled=False, title_template="Als nächstes", include_air_time=False
        )
    )
    coming_soon: GeneratedPromoVariantSettings = field(
        default_factory=lambda: GeneratedPromoVariantSettings(
            enabled=False, title_template="Coming soon", include_air_time=True
        )
    )
    lookahead_hours: int = 72
    min_gap_minutes: int = 20
    max_per_hour: int = 2
    promotable_min_duration_seconds: int = 300
    promotable_denied_tags: tuple[str, ...] = ("filler", "commercial", "bumper", "trailer", "countdown", "promo")


@dataclass(frozen=True, slots=True)
class FillerSettings:
    enabled: bool = False
    directories: tuple[Path, ...] = ()
    allowed_tags: tuple[str, ...] = ()
    denied_tags: tuple[str, ...] = ("movie",)
    max_duration_seconds: int = 900
    if_no_filler: str = "continue_current_mode"
    distribution: str = "anchor_bridge"
    insert_between_movies: bool = False
    max_consecutive_fillers: int = 3
    max_total_filler_block_seconds: int = 120
    prefer_filler_after_minutes: int = 45
    min_gap_between_filler_blocks_minutes: int = 20


@dataclass(frozen=True, slots=True)
class ProgramBlocksSettings:
    enabled: bool = False
    anchors: tuple[ProgramBlockAnchorSettings, ...] = ()
    blocks: tuple[ProgramBlockSettings, ...] = ()
    fillers: FillerSettings = field(default_factory=FillerSettings)
    generated_countdown: GeneratedCountdownSettings = field(default_factory=GeneratedCountdownSettings)
    generated_promos: GeneratedPromosSettings = field(default_factory=GeneratedPromosSettings)


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
    program_blocks: ProgramBlocksSettings = field(default_factory=ProgramBlocksSettings)


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
    program_blocks = raw.get("program_blocks", {}) or {}
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
        program_blocks=_program_blocks_from_mapping(program_blocks),
        media=MediaSettings(
            directories=directories,
            tag_file=Path(media["tag_file"]) if media.get("tag_file") else None,
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


def _program_blocks_from_mapping(raw: dict) -> ProgramBlocksSettings:
    anchors = tuple(_program_anchor_from_mapping(item) for item in raw.get("anchors", []) or [])
    blocks = tuple(_program_block_from_mapping(item) for item in raw.get("blocks", []) or [])
    fillers = raw.get("fillers", {}) or {}
    countdown = raw.get("generated_countdown", {}) or {}
    promos = raw.get("generated_promos", {}) or {}
    return ProgramBlocksSettings(
        enabled=bool(raw.get("enabled", False)),
        anchors=anchors,
        blocks=blocks,
        fillers=FillerSettings(
            enabled=bool(fillers.get("enabled", False)),
            directories=tuple(Path(item) for item in fillers.get("directories", []) or []),
            allowed_tags=tuple(_normalize_tag(item) for item in fillers.get("allowed_tags", []) or []),
            denied_tags=tuple(_normalize_tag(item) for item in fillers.get("denied_tags", ["movie"]) or []),
            max_duration_seconds=int(fillers.get("max_duration_seconds", 900)),
            if_no_filler=str(fillers.get("if_no_filler", "continue_current_mode")),
            distribution=str(fillers.get("distribution", "anchor_bridge")),
            insert_between_movies=bool(fillers.get("insert_between_movies", False)),
            max_consecutive_fillers=int(fillers.get("max_consecutive_fillers", 3)),
            max_total_filler_block_seconds=int(fillers.get("max_total_filler_block_seconds", 120)),
            prefer_filler_after_minutes=int(fillers.get("prefer_filler_after_minutes", 45)),
            min_gap_between_filler_blocks_minutes=int(fillers.get("min_gap_between_filler_blocks_minutes", 20)),
        ),
        generated_countdown=GeneratedCountdownSettings(
            enabled=bool(countdown.get("enabled", False)),
            max_duration_seconds=int(countdown.get("max_duration_seconds", 60)),
            title=str(countdown.get("title", "Gleich geht's weiter")),
        ),
        generated_promos=_generated_promos_from_mapping(promos),
    )


def _generated_promos_from_mapping(raw: dict) -> GeneratedPromosSettings:
    next_up = raw.get("next_up", {}) or {}
    coming_soon = raw.get("coming_soon", {}) or {}
    promotable = raw.get("promotable", {}) or {}
    return GeneratedPromosSettings(
        enabled=bool(raw.get("enabled", False)),
        duration_min_seconds=int(raw.get("duration_min_seconds", 15)),
        duration_max_seconds=int(raw.get("duration_max_seconds", 30)),
        next_up=GeneratedPromoVariantSettings(
            enabled=bool(next_up.get("enabled", False)),
            title_template=str(next_up.get("title_template", "Als nächstes")),
            include_air_time=bool(next_up.get("include_air_time", False)),
        ),
        coming_soon=GeneratedPromoVariantSettings(
            enabled=bool(coming_soon.get("enabled", False)),
            title_template=str(coming_soon.get("title_template", "Coming soon")),
            include_air_time=bool(coming_soon.get("include_air_time", True)),
        ),
        lookahead_hours=int(raw.get("lookahead_hours", 72)),
        min_gap_minutes=int(raw.get("min_gap_minutes", 20)),
        max_per_hour=int(raw.get("max_per_hour", 2)),
        promotable_min_duration_seconds=int(promotable.get("min_duration_seconds", raw.get("promotable_min_duration_seconds", 300))),
        promotable_denied_tags=tuple(
            _normalize_tag(item)
            for item in promotable.get(
                "denied_tags",
                raw.get("promotable_denied_tags", ["filler", "commercial", "bumper", "trailer", "countdown", "promo"]),
            )
            or []
        ),
    )


def _program_anchor_from_mapping(raw: dict) -> ProgramBlockAnchorSettings:
    return ProgramBlockAnchorSettings(
        enabled=bool(raw.get("enabled", False)),
        time=str(raw.get("time", "20:15")),
        title=str(raw.get("title", "Der 20:15 Film")),
        allowed_tags=tuple(_normalize_tag(item) for item in raw.get("allowed_tags", []) or []),
        denied_tags=tuple(_normalize_tag(item) for item in raw.get("denied_tags", []) or []),
        tag_match=str(raw.get("tag_match", "any")),
    )


def _program_block_from_mapping(raw: dict) -> ProgramBlockSettings:
    return ProgramBlockSettings(
        enabled=bool(raw.get("enabled", False)),
        start=str(raw.get("start", "06:00")),
        duration_seconds=_parse_duration_seconds(raw.get("duration", raw.get("duration_seconds", "02:30:00"))),
        title=str(raw.get("title", "PrivateTV Block")),
        allowed_tags=tuple(_normalize_tag(item) for item in raw.get("allowed_tags", []) or []),
        denied_tags=tuple(_normalize_tag(item) for item in raw.get("denied_tags", []) or []),
        tag_match=str(raw.get("tag_match", "any")),
        if_empty=str(raw.get("if_empty", "continue_current_mode")),
    )


def _parse_duration_seconds(value: object) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    parts = text.split(":")
    try:
        if len(parts) == 2:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = 0
        elif len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
        else:
            raise ValueError
    except ValueError as exc:
        raise ConfigurationError(f"Invalid program block duration: {value}") from exc
    if minutes > 59 or seconds > 59:
        raise ConfigurationError(f"Invalid program block duration: {value}")
    return hours * 3600 + minutes * 60 + seconds


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _normalize_tag(value: object) -> str:
    return str(value).strip().lower().replace(" ", "_")


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
    if settings.program_blocks.generated_countdown.max_duration_seconds < 1:
        raise ConfigurationError("program_blocks.generated_countdown.max_duration_seconds must be at least 1")
    if settings.program_blocks.generated_countdown.max_duration_seconds > 60:
        raise ConfigurationError("program_blocks.generated_countdown.max_duration_seconds must not be greater than 60")
    promos = settings.program_blocks.generated_promos
    if promos.duration_min_seconds < 1:
        raise ConfigurationError("program_blocks.generated_promos.duration_min_seconds must be at least 1")
    if promos.duration_max_seconds < promos.duration_min_seconds:
        raise ConfigurationError("program_blocks.generated_promos.duration_max_seconds must not be smaller than duration_min_seconds")
    if promos.duration_max_seconds > 60:
        raise ConfigurationError("program_blocks.generated_promos.duration_max_seconds must not be greater than 60")
    if promos.promotable_min_duration_seconds < 1:
        raise ConfigurationError("program_blocks.generated_promos.promotable.min_duration_seconds must be at least 1")
    for anchor in settings.program_blocks.anchors:
        if anchor.tag_match not in {"any", "all"}:
            raise ConfigurationError("program_blocks.anchors[].tag_match must be any or all")
    for block in settings.program_blocks.blocks:
        if block.tag_match not in {"any", "all"}:
            raise ConfigurationError("program_blocks.blocks[].tag_match must be any or all")
        if block.duration_seconds < 60:
            raise ConfigurationError("program_blocks.blocks[].duration must be at least 60 seconds")
        if block.duration_seconds > 24 * 3600:
            raise ConfigurationError("program_blocks.blocks[].duration must not be greater than 24 hours")
        if block.if_empty not in {"continue_current_mode", "skip_block"}:
            raise ConfigurationError("program_blocks.blocks[].if_empty must be continue_current_mode or skip_block")
    if settings.program_blocks.fillers.max_duration_seconds < 1:
        raise ConfigurationError("program_blocks.fillers.max_duration_seconds must be at least 1")
    if settings.program_blocks.fillers.if_no_filler not in {"continue_current_mode", "start_anchor_late", "skip_anchor"}:
        raise ConfigurationError("program_blocks.fillers.if_no_filler must be continue_current_mode, start_anchor_late, or skip_anchor")
    if settings.program_blocks.fillers.distribution not in {"anchor_bridge", "between_programmes"}:
        raise ConfigurationError("program_blocks.fillers.distribution must be anchor_bridge or between_programmes")
    if settings.program_blocks.fillers.max_consecutive_fillers < 1:
        raise ConfigurationError("program_blocks.fillers.max_consecutive_fillers must be at least 1")
    if settings.program_blocks.fillers.max_total_filler_block_seconds < 1:
        raise ConfigurationError("program_blocks.fillers.max_total_filler_block_seconds must be at least 1")
    if settings.program_blocks.fillers.prefer_filler_after_minutes < 1:
        raise ConfigurationError("program_blocks.fillers.prefer_filler_after_minutes must be at least 1")
    if settings.program_blocks.fillers.min_gap_between_filler_blocks_minutes < 0:
        raise ConfigurationError("program_blocks.fillers.min_gap_between_filler_blocks_minutes must not be negative")
    for anchor in settings.program_blocks.anchors:
        _validate_anchor_time(anchor.time)
    for block in settings.program_blocks.blocks:
        _validate_anchor_time(block.start)
    if not settings.streaming.output_container.strip():
        raise ConfigurationError("streaming.output_container must not be empty")
    _ = settings.schedule.zoneinfo



def _validate_anchor_time(value: str) -> None:
    parts = value.split(":")
    if len(parts) != 2:
        raise ConfigurationError(f"Invalid program block anchor time: {value}")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ConfigurationError(f"Invalid program block anchor time: {value}") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ConfigurationError(f"Invalid program block anchor time: {value}")


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
        "program_blocks": {
            "enabled": settings.program_blocks.enabled,
            "anchors": [
                {
                    "enabled": anchor.enabled,
                    "time": anchor.time,
                    "title": anchor.title,
                    "allowed_tags": list(anchor.allowed_tags),
                    "denied_tags": list(anchor.denied_tags),
                    "tag_match": anchor.tag_match,
                }
                for anchor in settings.program_blocks.anchors
            ],
            "blocks": [
                {
                    "enabled": block.enabled,
                    "start": block.start,
                    "duration": _format_duration(block.duration_seconds),
                    "title": block.title,
                    "allowed_tags": list(block.allowed_tags),
                    "denied_tags": list(block.denied_tags),
                    "tag_match": block.tag_match,
                    "if_empty": block.if_empty,
                }
                for block in settings.program_blocks.blocks
            ],
            "fillers": {
                "enabled": settings.program_blocks.fillers.enabled,
                "directories": [str(directory) for directory in settings.program_blocks.fillers.directories],
                "allowed_tags": list(settings.program_blocks.fillers.allowed_tags),
                "denied_tags": list(settings.program_blocks.fillers.denied_tags),
                "max_duration_seconds": settings.program_blocks.fillers.max_duration_seconds,
                "if_no_filler": settings.program_blocks.fillers.if_no_filler,
                "distribution": settings.program_blocks.fillers.distribution,
                "insert_between_movies": settings.program_blocks.fillers.insert_between_movies,
                "max_consecutive_fillers": settings.program_blocks.fillers.max_consecutive_fillers,
                "max_total_filler_block_seconds": settings.program_blocks.fillers.max_total_filler_block_seconds,
                "prefer_filler_after_minutes": settings.program_blocks.fillers.prefer_filler_after_minutes,
                "min_gap_between_filler_blocks_minutes": settings.program_blocks.fillers.min_gap_between_filler_blocks_minutes,
            },
            "generated_countdown": {
                "enabled": settings.program_blocks.generated_countdown.enabled,
                "max_duration_seconds": settings.program_blocks.generated_countdown.max_duration_seconds,
                "title": settings.program_blocks.generated_countdown.title,
            },
            "generated_promos": {
                "enabled": settings.program_blocks.generated_promos.enabled,
                "duration_min_seconds": settings.program_blocks.generated_promos.duration_min_seconds,
                "duration_max_seconds": settings.program_blocks.generated_promos.duration_max_seconds,
                "lookahead_hours": settings.program_blocks.generated_promos.lookahead_hours,
                "min_gap_minutes": settings.program_blocks.generated_promos.min_gap_minutes,
                "max_per_hour": settings.program_blocks.generated_promos.max_per_hour,
                "next_up": {
                    "enabled": settings.program_blocks.generated_promos.next_up.enabled,
                    "title_template": settings.program_blocks.generated_promos.next_up.title_template,
                    "include_air_time": settings.program_blocks.generated_promos.next_up.include_air_time,
                },
                "coming_soon": {
                    "enabled": settings.program_blocks.generated_promos.coming_soon.enabled,
                    "title_template": settings.program_blocks.generated_promos.coming_soon.title_template,
                    "include_air_time": settings.program_blocks.generated_promos.coming_soon.include_air_time,
                },
                "promotable": {
                    "min_duration_seconds": settings.program_blocks.generated_promos.promotable_min_duration_seconds,
                    "denied_tags": list(settings.program_blocks.generated_promos.promotable_denied_tags),
                },
            },
        },
        "media": {
            "directories": [str(directory) for directory in settings.media.directories],
            "tag_file": str(settings.media.tag_file) if settings.media.tag_file else "",
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
