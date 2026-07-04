# Patch 09: Technical Spikes

Patch 09 catches up the technical-spike step from the implementation concept. Patch 08 added schedule maintenance, which is useful and remains in place, but it did not cover the intended risk probes.

## Added

- `privatetv spike-seek`
  - documents the V1.0 seek strategy
  - prints the FFmpeg command shape
  - makes the accepted keyframe-aligned seek tolerance explicit
- `privatetv spike-dvd-concat`
  - builds candidate commands for DVD VOB playback
  - compares concat demuxer with `-fflags +genpts` against the concat protocol
  - can optionally execute both candidates against real VOB files
- `privatetv spike-tvh-upstream`
  - starts a small manual probe server
  - exposes `/probe.m3u`, `/probe.ts`, and `/status`
  - allows checking whether tvheadend opens one or multiple upstream connections when several clients watch the same IPTV channel
- Unit tests for all spike helpers

## Acceptance Criteria

- `pytest -q` is green.
- `privatetv spike-seek --config config/privatetv.example.yml` prints the accepted V1.0 seek policy.
- `privatetv spike-dvd-concat --config config/privatetv.example.yml <vob...>` builds both candidate commands without executing them.
- `privatetv spike-tvh-upstream --host 0.0.0.0 --port 9998` exposes a test M3U and connection status endpoint for manual tvheadend testing.

## Notes

The spike commands are intentionally diagnostic tools. They do not change normal streaming behavior by themselves. Their purpose is to make the risky integration points visible and repeatable before the final tvheadend acceptance.
