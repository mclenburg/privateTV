# Patch 16 - Scan resilience and visible progress

This patch improves the first-run media scan on large libraries.

## Changes

- `privatetv scan` now prints progress while probing files and DVD structures.
- Scan results are written to SQLite incrementally instead of only after the full scan finished.
- One failed database write no longer aborts the whole scan.
- File names containing surrogate characters from non-UTF-8 filesystem names are skipped safely and reported as invalid instead of crashing SQLite with `UnicodeEncodeError`.
- Scan summary now includes skipped files and probe/store failures.

## Operational impact

The scan command remains idempotent. It can be restarted after a failure and will update already imported records.

Malformed legacy filenames should still be renamed to proper UTF-8 names when possible, but they no longer stop the entire import run.

## Validation

- `python3 -m compileall -q src tests`
- `python3 -m pytest -q`
- Result: `65 passed`
