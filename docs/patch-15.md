# Patch 15 – review fixes and hardening

This patch addresses the concrete findings from the external code review.

Changes:

- fixes relative media root handling in both scanners:
  - `MediaItem.source_root` is now stored as an absolute path
  - `MediaAsset.path` is now stored as an absolute path
  - this prevents FFmpeg concat files in `/tmp` from resolving DVD VOB parts relative to `/tmp`
- adds regression tests for relative `media.directories` entries for local files and DVD structures
- removes the unused `runtime_stream` schema table from the initial schema
- removes the unused `schedule.allow_overflow_across_days` configuration field from settings, YAML roundtrips, the web UI, and the example config
- changes schedule insertion to `executemany()`
- avoids mutating the started aiohttp application mapping when saving config by keeping mutable runtime services in a dedicated runtime container
- strengthens the README warning for the unauthenticated configuration UI

Existing databases may still contain an old `runtime_stream` table from previous development builds. It is ignored by the application. A future migration system can drop it explicitly if needed.
