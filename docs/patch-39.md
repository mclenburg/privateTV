# Patch 39 - Robust short-duration probing and scheduler guards

This patch fixes the EPG burst caused by broken AVI duration metadata and DVD helper artifacts.

## Changes

- `ffprobe` fallback for suspiciously short normal video files:
  - if container duration is below 60 seconds but the file is large and has video,
  - count video packets and divide by frame rate,
  - use the packet-count duration when it is plausible.
- Normal programme candidates shorter than 60 seconds are no longer scheduled as regular content.
  Short items must be explicit fillers, countdowns, promos, or DVD extra fillers.
- Common DVD work artifacts such as `total.vob`, `concat.vob`, `merged.vob`, `joined.vob`, and `combined.vob` are skipped when they sit inside a DVD rip directory.

## Example

A broken AVI reporting `00:00:00.51` with `100896` video packets at `25 fps` is imported as roughly `4035.84` seconds instead.
