from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from aiohttp import web

from privatetv.config import AppSettings, settings_from_mapping, settings_to_mapping, write_settings
from privatetv.http.keys import CONFIG_PATH_KEY, RUNTIME_KEY
from privatetv.domain.errors import ConfigurationError


def render_config_page(
    settings: AppSettings,
    *,
    config_path: Path | None,
    message: str | None = None,
    error: str | None = None,
) -> str:
    data = settings_to_mapping(settings)
    return _page(
        "PrivateTV configuration",
        f"""
        <p class="lead">Edit the server-side PrivateTV configuration. Media directories are paths on the Raspberry Pi or server running PrivateTV, not paths on the browser client.</p>
        {_notice(message, 'ok') if message else ''}
        {_notice(error, 'error') if error else ''}
        {_readonly_warning(config_path)}
        <form method="post" action="/config" class="card">
          <h2>Server</h2>
          {_input('server.host', data['server']['host'])}
          {_input('server.port', data['server']['port'], input_type='number')}
          {_input('server.public_base_url', data['server']['public_base_url'])}

          <h2>Main channel</h2>
          <p class="hint">Leave <code>channel.icon</code> empty to use the built-in PrivateTV logo.</p>
          {_input('channel.id', data['channel']['id'])}
          {_input('channel.name', data['channel']['name'])}
          {_input('channel.icon', data['channel']['icon'])}
          {_input('channel.group_title', data['channel']['group_title'])}
          {_input('channel.language', data['channel']['language'])}

          <h2>Hazard TV</h2>
          <p class="hint">Leave <code>hazard_channel.icon</code> empty to use the built-in Hazard TV logo.</p>
          {_checkbox('hazard_channel.enabled', data['hazard_channel']['enabled'])}
          {_input('hazard_channel.id', data['hazard_channel']['id'])}
          {_input('hazard_channel.name', data['hazard_channel']['name'])}
          {_input('hazard_channel.icon', data['hazard_channel']['icon'])}
          {_input('hazard_channel.group_title', data['hazard_channel']['group_title'])}
          {_input('hazard_channel.language', data['hazard_channel']['language'])}
          {_input('hazard_channel.random_seed', data['hazard_channel']['random_seed'] if data['hazard_channel']['random_seed'] is not None else '', input_type='number')}
          {_checkbox('hazard_channel.avoid_immediate_repeat', data['hazard_channel']['avoid_immediate_repeat'])}

          <h2>Media</h2>
          <label>media.directories <span>one server-side path per line</span>
            <textarea name="media.directories" rows="6">{_escape(_lines(data['media']['directories']))}</textarea>
          </label>
          <p><a class="button secondary" href="/config/browse">Browse server directories</a></p>
          {_checkbox('media.recursive', data['media']['recursive'])}
          {_checkbox('media.follow_symlinks', data['media']['follow_symlinks'])}
          {_checkbox('media.ignore_hidden_directories', data['media']['ignore_hidden_directories'])}
          <label>media.extensions <span>one extension per line</span>
            <textarea name="media.extensions" rows="5">{_escape(_lines(data['media']['extensions']))}</textarea>
          </label>

          <h2>DVD detection</h2>
          {_checkbox('media.dvd.enabled', data['media']['dvd']['enabled'])}
          {_checkbox('media.dvd.detect_video_ts', data['media']['dvd']['detect_video_ts'])}
          {_input('media.dvd.main_title_strategy', data['media']['dvd']['main_title_strategy'])}
          {_input('media.dvd.min_main_title_size_mb', data['media']['dvd']['min_main_title_size_mb'], input_type='number')}
          {_input('media.dvd.min_main_title_duration_seconds', data['media']['dvd']['min_main_title_duration_seconds'], input_type='number')}

          <h2>Schedule</h2>
          {_input('schedule.minimum_days_ahead', data['schedule']['minimum_days_ahead'], input_type='number')}
          {_input('schedule.days_ahead', data['schedule']['days_ahead'], input_type='number')}
          {_input('schedule.timezone', data['schedule']['timezone'])}
          {_input('schedule.rebuild_hour', data['schedule']['rebuild_hour'], input_type='number')}
          {_select('schedule.strategy', data['schedule']['strategy'], ['shuffle_no_repeat', 'alphabetical'])}
          {_input('schedule.random_seed', data['schedule']['random_seed'] if data['schedule']['random_seed'] is not None else '', input_type='number')}

          <h2>Program blocks</h2>
          <p class="hint">Experimental broadcast automation scaffolding. Keep disabled to preserve the current continuous film-after-film scheduler.</p>
          {_checkbox('program_blocks.enabled', data['program_blocks']['enabled'])}
          {_checkbox('program_blocks.anchors.0.enabled', _first_anchor(data)['enabled'])}
          {_input('program_blocks.anchors.0.time', _first_anchor(data)['time'])}
          {_input('program_blocks.anchors.0.title', _first_anchor(data)['title'])}
          <label>program_blocks.anchors.0.allowed_tags <span>one tag per line</span>
            <textarea name="program_blocks.anchors.0.allowed_tags" rows="3">{_escape(_lines(_first_anchor(data)['allowed_tags']))}</textarea>
          </label>
          {_checkbox('program_blocks.fillers.enabled', data['program_blocks']['fillers']['enabled'])}
          <label>program_blocks.fillers.directories <span>one server-side path per line</span>
            <textarea name="program_blocks.fillers.directories" rows="3">{_escape(_lines(data['program_blocks']['fillers']['directories']))}</textarea>
          </label>
          {_input('program_blocks.fillers.max_duration_seconds', data['program_blocks']['fillers'].get('max_duration_seconds', 900), input_type='number')}
          {_select('program_blocks.fillers.if_no_filler', data['program_blocks']['fillers']['if_no_filler'], ['continue_current_mode', 'start_anchor_late', 'skip_anchor'])}
          {_checkbox('program_blocks.generated_countdown.enabled', data['program_blocks']['generated_countdown']['enabled'])}
          {_input('program_blocks.generated_countdown.max_duration_seconds', data['program_blocks']['generated_countdown']['max_duration_seconds'], input_type='number')}
          {_input('program_blocks.generated_countdown.title', data['program_blocks']['generated_countdown']['title'])}

          <h2>Streaming</h2>
          {_input('streaming.max_parallel_streams', data['streaming']['max_parallel_streams'], input_type='number')}
          {_input('streaming.output_container', data['streaming']['output_container'])}
          {_checkbox('streaming.prefer_stream_copy', data['streaming']['prefer_stream_copy'])}
          {_checkbox('streaming.transcode_when_needed', data['streaming']['transcode_when_needed'])}
          {_input('streaming.ffmpeg_path', data['streaming']['ffmpeg_path'])}
          {_input('streaming.ffprobe_path', data['streaming']['ffprobe_path'])}
          {_input('streaming.accepted_seek_tolerance_seconds', data['streaming']['accepted_seek_tolerance_seconds'], input_type='number')}

          <h2>Database and logging</h2>
          {_input('database.path', data['database']['path'])}
          {_select('logging.level', data['logging']['level'], ['DEBUG', 'INFO', 'WARNING', 'ERROR'])}

          <button type="submit">Save configuration</button>
        </form>
        """,
    )


def _first_anchor(data: dict) -> dict:
    anchors = data.get("program_blocks", {}).get("anchors", [])
    if anchors:
        return anchors[0]
    return {"enabled": False, "time": "20:15", "title": "Der 20:15 Film", "allowed_tags": ["movie"]}


async def show_config(request: web.Request) -> web.Response:
    settings = _settings(request.app)
    config_path = request.app.get(CONFIG_PATH_KEY)
    return web.Response(text=render_config_page(settings, config_path=config_path), content_type="text/html")


async def save_config(request: web.Request) -> web.Response:
    current_settings = _settings(request.app)
    config_path = request.app.get(CONFIG_PATH_KEY)
    if config_path is None:
        return web.Response(
            text=render_config_page(
                current_settings,
                config_path=None,
                error="This service was started without a writable configuration path.",
            ),
            content_type="text/html",
            status=400,
        )
    form = await request.post()
    raw = _form_to_mapping(form)
    try:
        new_settings = settings_from_mapping(raw)
        write_settings(config_path, new_settings)
    except (ConfigurationError, OSError, ValueError) as exc:
        return web.Response(
            text=render_config_page(current_settings, config_path=config_path, error=str(exc)),
            content_type="text/html",
            status=400,
        )
    _refresh_runtime_services(request.app, new_settings)
    return web.Response(
        text=render_config_page(new_settings, config_path=config_path, message=f"Saved {config_path}"),
        content_type="text/html",
    )


async def browse_directories(request: web.Request) -> web.Response:
    settings = _settings(request.app)
    raw_path = request.query.get("path") or _default_browse_path(settings)
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    if not path.exists() or not path.is_dir():
        path = Path("/")
    try:
        entries = sorted(
            [item for item in path.iterdir() if item.is_dir()],
            key=lambda item: item.name.lower(),
        )
    except PermissionError:
        entries = []
    parent = path.parent if path != path.parent else path
    rows = [
        f'<li><a href="/config/browse?path={_url(parent)}">..</a></li>',
        f'<li><form method="post" action="/config/media-directories/add">'
        f'<input type="hidden" name="path" value="{_escape(str(path))}">'
        f'<button type="submit">Add this server directory</button> '
        f'<code>{_escape(str(path))}</code></form></li>',
    ]
    rows.extend(
        f'<li><a href="/config/browse?path={_url(entry)}">{_escape(entry.name)}/</a></li>'
        for entry in entries
    )
    return web.Response(
        text=_page(
            "Browse server directories",
            f"""
            <p class="lead">Select directories from the filesystem of the PrivateTV server. This is not a browser file upload.</p>
            <p><a href="/config">Back to configuration</a></p>
            <div class="card"><h2>{_escape(str(path))}</h2><ul class="browser">{''.join(rows)}</ul></div>
            """,
        ),
        content_type="text/html",
    )


async def add_media_directory(request: web.Request) -> web.Response:
    settings = _settings(request.app)
    config_path = request.app.get(CONFIG_PATH_KEY)
    form = await request.post()
    directory = Path(str(form.get("path", ""))).expanduser()
    if not directory.is_absolute():
        directory = directory.resolve()
    if not directory.exists() or not directory.is_dir():
        return web.Response(
            text=render_config_page(settings, config_path=config_path, error=f"Not a server directory: {directory}"),
            content_type="text/html",
            status=400,
        )
    raw = settings_to_mapping(settings)
    directories = list(raw["media"]["directories"])
    if str(directory) not in directories:
        directories.append(str(directory))
    raw["media"]["directories"] = directories
    try:
        new_settings = settings_from_mapping(raw)
        if config_path is not None:
            write_settings(config_path, new_settings)
    except (ConfigurationError, OSError) as exc:
        return web.Response(
            text=render_config_page(settings, config_path=config_path, error=str(exc)),
            content_type="text/html",
            status=400,
        )
    _refresh_runtime_services(request.app, new_settings)
    return web.Response(
        text=render_config_page(new_settings, config_path=config_path, message=f"Added {directory}"),
        content_type="text/html",
    )


def _settings(app: web.Application) -> AppSettings:
    return app[RUNTIME_KEY]["settings"]


def _refresh_runtime_services(app: web.Application, settings: AppSettings) -> None:
    # Import lazily to avoid a config-ui dependency cycle during tests.
    from privatetv.hazard import HazardRandomStreamProvider
    from privatetv.http.server import StreamState
    from privatetv.streaming import PerClientFfmpegStreamProvider

    runtime = app[RUNTIME_KEY]
    provider = PerClientFfmpegStreamProvider(settings)
    runtime["settings"] = settings
    runtime["stream_provider"] = provider
    runtime["hazard_provider"] = HazardRandomStreamProvider(settings, provider)
    current_state = runtime["stream_state"]
    if current_state.active_streams == 0:
        runtime["stream_state"] = StreamState(settings.streaming.max_parallel_streams)


def _form_to_mapping(form: Any) -> dict:
    def text(name: str, default: str = "") -> str:
        return str(form.get(name, default)).strip()

    def integer(name: str, default: int) -> int:
        raw = text(name, str(default))
        if raw == "":
            return default
        return int(raw)

    def optional_integer(name: str) -> int | None:
        raw = text(name, "")
        return None if raw == "" else int(raw)

    def checkbox(name: str) -> bool:
        return form.get(name) == "on"

    def lines(name: str) -> list[str]:
        return [line.strip() for line in str(form.get(name, "")).splitlines() if line.strip()]

    return {
        "server": {
            "host": text("server.host", "127.0.0.1"),
            "port": integer("server.port", 9988),
            "public_base_url": text("server.public_base_url", "http://127.0.0.1:9988"),
        },
        "channel": {
            "id": text("channel.id", "privatetv"),
            "name": text("channel.name", "PrivateTV"),
            "icon": text("channel.icon"),
            "group_title": text("channel.group_title", "Local"),
            "language": text("channel.language", "de"),
        },
        "hazard_channel": {
            "enabled": checkbox("hazard_channel.enabled"),
            "id": text("hazard_channel.id", "hazardtv"),
            "name": text("hazard_channel.name", "Hazard TV"),
            "icon": text("hazard_channel.icon"),
            "group_title": text("hazard_channel.group_title", "Local"),
            "language": text("hazard_channel.language", "de"),
            "random_seed": optional_integer("hazard_channel.random_seed"),
            "avoid_immediate_repeat": checkbox("hazard_channel.avoid_immediate_repeat"),
        },
        "media": {
            "directories": lines("media.directories"),
            "recursive": checkbox("media.recursive"),
            "follow_symlinks": checkbox("media.follow_symlinks"),
            "ignore_hidden_directories": checkbox("media.ignore_hidden_directories"),
            "extensions": lines("media.extensions"),
            "dvd": {
                "enabled": checkbox("media.dvd.enabled"),
                "detect_video_ts": checkbox("media.dvd.detect_video_ts"),
                "main_title_strategy": text("media.dvd.main_title_strategy", "largest_titleset"),
                "min_main_title_size_mb": integer("media.dvd.min_main_title_size_mb", 500),
                "min_main_title_duration_seconds": integer("media.dvd.min_main_title_duration_seconds", 1200),
            },
        },
        "schedule": {
            "minimum_days_ahead": integer("schedule.minimum_days_ahead", 3),
            "days_ahead": integer("schedule.days_ahead", 5),
            "timezone": text("schedule.timezone", "Europe/Berlin"),
            "rebuild_hour": integer("schedule.rebuild_hour", 3),
            "strategy": text("schedule.strategy", "shuffle_no_repeat"),
            "random_seed": optional_integer("schedule.random_seed"),
        },
        "program_blocks": {
            "enabled": checkbox("program_blocks.enabled"),
            "anchors": [
                {
                    "enabled": checkbox("program_blocks.anchors.0.enabled"),
                    "time": text("program_blocks.anchors.0.time", "20:15"),
                    "title": text("program_blocks.anchors.0.title", "Der 20:15 Film"),
                    "allowed_tags": lines("program_blocks.anchors.0.allowed_tags"),
                }
            ],
            "fillers": {
                "enabled": checkbox("program_blocks.fillers.enabled"),
                "directories": lines("program_blocks.fillers.directories"),
                "max_duration_seconds": integer("program_blocks.fillers.max_duration_seconds", 900),
                "if_no_filler": text("program_blocks.fillers.if_no_filler", "continue_current_mode"),
            },
            "generated_countdown": {
                "enabled": checkbox("program_blocks.generated_countdown.enabled"),
                "max_duration_seconds": integer("program_blocks.generated_countdown.max_duration_seconds", 60),
                "title": text("program_blocks.generated_countdown.title", "Gleich geht's weiter"),
            },
        },
        "streaming": {
            "max_parallel_streams": integer("streaming.max_parallel_streams", 4),
            "output_container": text("streaming.output_container", "mpegts"),
            "prefer_stream_copy": checkbox("streaming.prefer_stream_copy"),
            "transcode_when_needed": checkbox("streaming.transcode_when_needed"),
            "ffmpeg_path": text("streaming.ffmpeg_path", "/usr/bin/ffmpeg"),
            "ffprobe_path": text("streaming.ffprobe_path", "/usr/bin/ffprobe"),
            "accepted_seek_tolerance_seconds": integer("streaming.accepted_seek_tolerance_seconds", 10),
        },
        "database": {"path": text("database.path", "var/lib/privatetv/privatetv.sqlite3")},
        "logging": {"level": text("logging.level", "INFO")},
    }


def _default_browse_path(settings: AppSettings) -> str:
    for directory in settings.media.directories:
        if directory.exists() and directory.is_dir():
            return str(directory)
    return "/"


def _readonly_warning(config_path: Path | None) -> str:
    if config_path is None:
        return _notice("Configuration can be viewed but not saved because no config path is known.", "error")
    return f'<p class="muted">Config file: <code>{_escape(str(config_path))}</code></p>'


def _input(name: str, value: object, *, input_type: str = "text") -> str:
    return f'<label>{_escape(name)}<input type="{input_type}" name="{_escape(name)}" value="{_escape(str(value))}"></label>'


def _checkbox(name: str, checked: bool) -> str:
    flag = " checked" if checked else ""
    return f'<label class="check"><input type="checkbox" name="{_escape(name)}"{flag}> {_escape(name)}</label>'


def _select(name: str, value: str, options: list[str]) -> str:
    choices = []
    for option in options:
        selected = " selected" if option == value else ""
        choices.append(f'<option value="{_escape(option)}"{selected}>{_escape(option)}</option>')
    return f'<label>{_escape(name)}<select name="{_escape(name)}">{"".join(choices)}</select></label>'


def _notice(text: str, kind: str) -> str:
    return f'<p class="notice {kind}">{_escape(text)}</p>'


def _lines(values: list[str] | tuple[str, ...]) -> str:
    return "\n".join(str(value) for value in values)


def _url(path: Path) -> str:
    from urllib.parse import quote

    return quote(str(path), safe="")


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)} · PrivateTV</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
body {{ margin: 0; background: #111827; color: #f9fafb; }}
main {{ max-width: 980px; margin: 0 auto; padding: 2rem; }}
a {{ color: #93c5fd; }}
.lead {{ font-size: 1.1rem; line-height: 1.5; }}
.card {{ background: #1f2937; border: 1px solid #374151; border-radius: 14px; padding: 1.25rem; margin: 1rem 0; }}
h1, h2 {{ line-height: 1.2; }}
label {{ display: block; margin: 0.75rem 0; font-weight: 600; }}
label span, .muted {{ color: #9ca3af; font-size: .9rem; font-weight: 400; }}
input, textarea, select {{ width: 100%; box-sizing: border-box; margin-top: .25rem; padding: .6rem; border-radius: 8px; border: 1px solid #4b5563; background: #111827; color: #f9fafb; }}
.check {{ display: flex; align-items: center; gap: .5rem; }}
.check input {{ width: auto; }}
button, .button {{ display: inline-block; padding: .65rem 1rem; border: 0; border-radius: 999px; background: #2563eb; color: white; text-decoration: none; font-weight: 700; cursor: pointer; }}
.secondary {{ background: #374151; }}
.notice {{ padding: .75rem 1rem; border-radius: 10px; }}
.notice.ok {{ background: #064e3b; }}
.notice.error {{ background: #7f1d1d; }}
ul.browser {{ list-style: none; padding: 0; }}
ul.browser li {{ padding: .45rem 0; border-bottom: 1px solid #374151; }}
code {{ background: #111827; padding: .1rem .25rem; border-radius: 4px; }}
</style>
</head>
<body><main><h1>{_escape(title)}</h1>{body}</main></body>
</html>"""
