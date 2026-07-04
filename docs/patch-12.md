# Patch 12: hardening and defect corrections

This patch performs a focused hardening pass after the V1 feature set.

## Changes

- Raises the version to `0.12.0`.
- Removes dynamic `__import__` usage from the CLI and replaces it with explicit imports.
- Adds stricter configuration validation for:
  - HTTP(S) `server.public_base_url`
  - valid TCP port range
  - non-empty channel IDs
  - integer-or-null Hazard TV random seed
  - non-negative seek tolerance
  - non-empty FFmpeg output container
- Enables SQLite `busy_timeout` and WAL mode for more robust concurrent service/maintenance use.
- Validates current programme media before streaming:
  - media must still be enabled
  - media must have `ok` scan status
  - source kind must be streamable
  - referenced media assets must still exist
- Prepares HTTP stream responses only after the stream provider produced its first chunk.
  This allows startup failures to become structured JSON errors instead of a partially prepared MPEG-TS response.
- Maps FFmpeg stream-preparation errors to HTTP 503 instead of generic HTTP 500.
- Validates local and DVD asset paths before FFmpeg command creation.
- Fixes ffconcat path escaping for paths containing backslashes or single quotes.
- Adds a cleanup helper to remove generated package metadata and caches accidentally introduced by earlier patch archives.

## Cleanup

After applying this patch, run once from the repository root:

```bash
scripts/cleanup-patch-12.sh
```

## Verification

```bash
python3 -m compileall -q src tests
pytest -q
PYTHONPATH=src python3 -m privatetv --version
```

Expected test result at patch creation time:

```text
54 passed
PrivateTV 0.12.0
```
