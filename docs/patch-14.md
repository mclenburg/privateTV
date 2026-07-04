# Patch 14 – built-in channel logos in M3U

This patch adds built-in sender logos for the main PrivateTV channel and the optional Hazard TV channel.

Changes:

- adds packaged logo assets for `PrivateTV` and `Hazard TV`
- serves the built-in logos via the HTTP service:
  - `/logos/privatetv.png`
  - `/logos/hazardtv.png`
- updates M3U rendering so that empty `channel.icon` / `hazard_channel.icon` values automatically fall back to the built-in logo URLs
- keeps explicitly configured icon URLs unchanged
- updates the example configuration and the web configuration UI to document the built-in logo behavior
- intentionally does **not** enable logo overlays in the transport stream, because that would force video filtering and re-encoding and would reduce Raspberry-Pi-friendly parallel streaming capacity
