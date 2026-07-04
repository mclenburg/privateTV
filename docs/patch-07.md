# Patch 07: FFmpeg stream endpoint

Patch 07 replaces the stable stream placeholder with real per-client FFmpeg streaming.

## Added

- `PerClientFfmpegStreamProvider`
- `FfmpegCommandFactory`
- `/stream/main.ts` MPEG-TS streaming
- clock-based programme resolution and seek offset calculation
- media asset lookup for local files and DVD structures
- DVD concat command preparation with `-fflags +genpts`
- active stream accounting in `/health`
- maximum parallel stream enforcement
- tests for FFmpeg command generation and HTTP streaming

## Behaviour

When tvheadend opens `/stream/main.ts`, PrivateTV:

1. Resolves the schedule entry that is active at the current wall-clock time.
2. Calculates the offset inside that programme.
3. Loads the media assets belonging to the current item.
4. Starts one FFmpeg process for the client.
5. Streams FFmpeg stdout as `video/MP2T`.
6. Terminates FFmpeg when the HTTP client disconnects or the stream ends.

## Accepted limitation

Version 1.0 uses fast seek before input in stream-copy mode. This is efficient on Raspberry Pi hardware, but it is not frame-accurate for all containers and GOP layouts. The configured `accepted_seek_tolerance_seconds` documents the tolerated difference.

## Acceptance

Patch 07 is considered complete when:

- unit tests for local-file and DVD FFmpeg commands pass
- `/stream/main.ts` returns `503` when no current programme exists
- `/stream/main.ts` returns `video/MP2T` when a current programme exists
- active stream accounting remains visible in `/health`
- all existing tests remain green
