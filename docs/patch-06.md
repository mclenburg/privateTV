# Patch 06 - HTTP endpoints

Patch 6 turns the generated tvheadend outputs into HTTP endpoints.

## Added

- `GET /health`
  - reports service status, active stream count, configured stream limit, current programme, and schedule end
  - returns `degraded` when no future schedule exists
- `GET /playlist.m3u`
  - returns the tvheadend IPTV playlist
  - uses `audio/x-mpegurl`
  - disables caching
- `GET /xmltv.xml`
  - returns XMLTV generated from the stored schedule
  - uses dynamic timezone formatting from the configured zone
  - returns an empty channel document when no schedule exists
- `GET /stream/main.ts`
  - stable final stream URL
  - currently returns `501 Not Implemented`; FFmpeg streaming is Patch 7
- `GET /`
  - small JSON index for humans and smoke tests

## Changed

- Project version is now `0.6.0`.
- README now documents the HTTP service as a user-facing feature.

## Acceptance checks

```bash
pytest -q
PYTHONPATH=src python3 -m privatetv --version
PYTHONPATH=src python3 -m privatetv serve --config config/privatetv.example.yml
```

In another shell:

```bash
curl -fsS http://127.0.0.1:9988/health
curl -fsS http://127.0.0.1:9988/playlist.m3u
curl -fsS http://127.0.0.1:9988/xmltv.xml
curl -i http://127.0.0.1:9988/stream/main.ts
```

Expected stream status in Patch 6: `501 Not Implemented`.
