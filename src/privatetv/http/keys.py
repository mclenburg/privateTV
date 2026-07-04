from __future__ import annotations

from pathlib import Path

from aiohttp import web

from privatetv.config import AppSettings
from privatetv.hazard import HazardRandomStreamProvider
from privatetv.streaming import StreamProvider

SETTINGS_KEY = web.AppKey("settings", AppSettings)
CONFIG_PATH_KEY = web.AppKey("config_path", Path)
STREAM_PROVIDER_KEY = web.AppKey("stream_provider", StreamProvider)
HAZARD_PROVIDER_KEY = web.AppKey("hazard_provider", HazardRandomStreamProvider)
STREAM_STATE_KEY = web.AppKey("stream_state", object)
