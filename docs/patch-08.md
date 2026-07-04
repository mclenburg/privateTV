# Patch 08 - Schedule maintenance

Patch 08 makes the programme guide self-maintaining.

## Goals

- Keep the stored schedule long enough for tvheadend EPG imports.
- Treat 3 days as the minimum future horizon and 5 days as the target horizon by default.
- Extend the existing timeline without changing past or already scheduled entries.
- Reuse the same maintenance logic from CLI and HTTP/XMLTV generation.

## Changes

- Added `schedule.minimum_days_ahead` with default `3`.
- Added `ScheduleMaintainer`.
- Changed `privatetv schedule` to ensure the configured schedule horizon instead of blindly appending every time.
- Added `privatetv maintain-schedule` as an explicit command alias for schedule maintenance.
- XMLTV generation now runs schedule maintenance before reading programme entries.
- HTTP startup attempts schedule maintenance if media has already been scanned.
- `/health` now reports schedule horizon details:
  - `schedule_required_until`
  - `schedule_target_until`
  - `schedule_days_remaining`
  - `schedule_minimum_days_ahead`
  - `schedule_target_days_ahead`
  - `schedule_needs_extension`
- Updated the English project README.

## Acceptance criteria

- `privatetv schedule` extends an empty schedule up to the 5-day target horizon.
- `privatetv schedule` does not append duplicate entries when the stored schedule already reaches at least 3 days into the future.
- If the stored schedule only reaches less than 3 days into the future, PrivateTV appends new entries up to the 5-day target horizon.
- `/xmltv.xml` runs schedule maintenance before rendering XMLTV.
- `/health` is degraded when the stored schedule does not reach the minimum horizon.
- Unit tests pass.
