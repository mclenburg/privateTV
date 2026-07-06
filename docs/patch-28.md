# Patch 28 - Shared main-channel live stream

This patch changes the runtime streaming topology for the linear main channel.

## Changed

- `/stream/main.ts` now uses a shared live FFmpeg process with HTTP fanout.
- Multiple main-channel clients subscribe to the same running MPEG-TS byte stream.
- The shared FFmpeg process is stopped when the last main-channel client disconnects.
- A programme change starts a new shared main-channel FFmpeg session.
- `/stream/hazard.ts` deliberately keeps the previous per-client behaviour. Each Hazard TV request still receives an independent random media selection starting at offset 0.

## Why

The main channel is a linear TV station: all viewers should see the same programme at the same station time. Sharing the stream avoids running one expensive FFmpeg process per viewer, which is especially important when a problematic source requires transcoding.

Hazard TV is different: it is a personal random-pick channel. It must not use fanout because each viewer should receive their own randomly selected movie from the beginning.

## Validation

- Unit tests confirm that the default HTTP application uses the shared provider for the main channel and a per-client FFmpeg provider for Hazard TV.
- Existing HTTP, Hazard TV, streaming and scheduler tests remain green.

Tests: `93 passed`.
