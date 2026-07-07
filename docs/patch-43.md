# Patch 43 - Scheduler repeat guard and fanout subscriber eviction

This patch hardens two production-facing areas.

## Main content repeat guard

Normal main content (`video_file`, `dvd_main_title`, and other non-filler, non-generated, non-episode media) now uses an in-build repeat guard:

- do not repeat the same main media item while less than 80% of the eligible main-content pool has been used,
- do not schedule the same main media item more than once on the same calendar day while alternatives exist,
- avoid immediate repeats even in emergency fallback,
- exclude fillers, generated countdowns/promos, DVD extras and series episodes from this rule.

The guard is deliberately config-free for now so the safe behavior is the default.

## Shared main-channel fanout hardening

The shared live main stream no longer waits indefinitely for every subscriber queue. Each subscriber queue write is bounded by a short timeout. A stalled/full subscriber is actively evicted and the healthy subscribers continue receiving chunks.

This prevents a single half-dead Kodi/tvheadend/mobile client from freezing the whole main channel.

## Tests

Added regression coverage for:

- main content not repeating before the 80% rotation threshold,
- same-day main content repeat avoidance while alternatives exist,
- shared fanout evicting a stalled subscriber without blocking a healthy one.
