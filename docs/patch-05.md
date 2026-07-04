# Patch 05 - tvheadend playlist and XMLTV output

Patch 05 makes the tvheadend-facing text formats production-oriented while keeping actual HTTP streaming for a later patch.

## Added

- Stable tvheadend URL helpers for playlist, XMLTV and stream endpoints.
- M3U `url-tvg` metadata pointing at the XMLTV URL.
- Configurable channel group title and XMLTV language.
- Optional channel logo metadata in the M3U playlist.
- XMLTV `generator-info-url`, language-aware display names, programme category and duration.
- XMLTV entry validation for channel consistency, timezone-aware datetimes and positive durations.
- Pretty-printed XMLTV output for easier inspection and debugging.

## Changed

- README remains an English public project README.
- Project version is now `0.5.0`.
- The example configuration includes `channel.group_title` and `channel.language`.

## Acceptance criteria

- `privatetv m3u --config config/privatetv.example.yml` emits a single stable IPTV channel playlist.
- `privatetv xmltv --config config/privatetv.example.yml` emits valid XMLTV from the stored schedule.
- XMLTV timestamps use the configured time zone and dynamic daylight-saving offsets.
- XMLTV rejects mismatching channel IDs and naive datetimes instead of silently producing invalid EPG data.
- `pytest -q` passes.
