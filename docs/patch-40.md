# Patch 40 – DVD scanner sanity audit

Patch 40 hardens DVD duration detection after real DVD rips exposed implausible IFO play times such as `21:21:01`.

## Changes

- Reject implausible DVD PGC play times above six hours.
- Do not reinterpret an invalid primary `PGC_PLAY_TIME` field through the old fallback offset.
- Prefer the longest plausible title duration; IFO metadata is now a tie-breaker, not an unconditional trump card.
- Fall back to a concat-probed VOB title-set duration when IFO duration is missing or rejected.
- Skip implausible DVD main-title candidates instead of importing 20+ hour EPG entries.
- Keep generated/short extra handling unchanged.

## Why

Some copied/authored DVDs contain malformed IFO time fields. The scanner accepted those values and created huge programme entries, for example a 56 minute VTS became a 1281 minute EPG entry. The scanner now validates IFO time before using it.
