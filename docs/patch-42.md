# Patch 42: Streaming client disconnect handling

This patch treats client-side disconnects while streaming MPEG-TS as normal
runtime events instead of HTTP server failures.

## Fixed

- `aiohttp.client_exceptions.ClientConnectionResetError` during response writes
  is now logged at INFO level.
- Broken pipe / connection reset during stream writes no longer escapes to the
  channel handlers as `Failed to stream channel` / `Failed to stream Hazard TV`.
- The stream iterator is still closed, so shared main streams and per-client
  Hazard streams release their resources normally.

This is especially relevant when tvheadend, Kodi, or the local audio stack
(PipeWire/PulseAudio) restarts or switches outputs and closes the IPTV HTTP
connection while PrivateTV is still writing chunks.
