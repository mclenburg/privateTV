# Patch 10 - systemd packaging and Hazard TV preparation

## Scope

This patch adds the production operating files that were planned for the systemd/install step and prepares the configuration/M3U shape for the later Hazard TV channel.

## Added

- systemd units:
  - `privatetv.service`
  - `privatetv-scan.service`
  - `privatetv-scan.timer`
  - `privatetv-schedule.service`
  - `privatetv-schedule.timer`
- helper scripts:
  - `scripts/prepare-production-layout.sh`
  - `scripts/install-systemd.sh`
- tmpfiles template for `/etc/privatetv` and `/var/lib/privatetv`
- explicit production layout documentation
- optional `hazard_channel` configuration section
- optional second M3U channel when Hazard TV is enabled
- placeholder `/stream/hazard.ts` endpoint with clear not-implemented behavior

## Hazard TV decision

Hazard TV is deliberately not implemented as a full random stream provider in this patch. It is only modeled in the public shape:

- separate channel identity
- separate stable stream URL
- no XMLTV entries
- global stream limit remains shared

The actual random provider belongs in a later patch so the V1.0 systemd packaging remains focused.

## Verification

```bash
pytest -q
PYTHONPATH=src python3 -m privatetv --version
PYTHONPATH=src python3 -m privatetv m3u --config config/privatetv.example.yml
```
