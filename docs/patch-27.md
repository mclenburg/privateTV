# Patch 27 - Honor streaming transcode settings

This patch fixes a streaming bug where `streaming.prefer_stream_copy` and
`streaming.transcode_when_needed` were parsed from configuration but not used
when building FFmpeg commands.

## Changed

- FFmpeg command generation now honors `prefer_stream_copy: false` together with
  `transcode_when_needed: true`.
- Transcoded streams use H.264 video and AAC stereo audio for MPEG-TS output.
- Local-file streams now also request generated timestamps and avoid negative
  timestamps before MPEG-TS muxing.
- Regression tests cover local-file and DVD command generation in transcode mode.

## Why

Some source files fail with stream copy after seeking because the MPEG-TS muxer
receives packets without valid PTS/DTS values. In that situation FFmpeg emits
`first pts and dts value must be set` and terminates after only a few packets.
Transcoding regenerates valid timestamps and keeps the stream playable.
