# Patch 23: Distributed local fillers

Adds scheduler support for TV-like short filler distribution before configured anchors.

## New configuration

`program_blocks.fillers` now supports:

- `distribution`: `anchor_bridge` or `between_programmes`
- `insert_between_movies`: place short filler blocks after normal programmes when enough time has passed
- `max_consecutive_fillers`: limit how many filler clips may run back-to-back
- `max_total_filler_block_seconds`: limit the duration of one filler/ad block
- `prefer_filler_after_minutes`: approximate programme time before inserting a filler break
- `min_gap_between_filler_blocks_minutes`: reserved for spacing consecutive filler breaks

Defaults keep existing behavior. With `distribution: anchor_bridge`, PrivateTV behaves like patch 20.

## Behavior

With `distribution: between_programmes` and `insert_between_movies: true`, PrivateTV can use short local clips such as commercials, bumpers, trailers, or DVD previews between normal programmes instead of placing all filler material immediately before the anchor. The generated countdown remains the final fine adjustment and is still capped at 60 seconds.

## Filler media types

The scheduler treats the following media types as filler-like clips:

- `filler`
- `trailer`
- `bumper`
- `commercial`
- `advertisement`
- `dvd_preview`

The current scanner still imports configured filler directories as `filler`; the broader list prepares later scanners/importers.
