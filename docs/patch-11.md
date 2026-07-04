# Patch 11 - Hazard TV random channel

This patch implements the optional Hazard TV channel that was prepared in patch 10.

## Added

- Hazard TV random stream provider
- `/stream/hazard.ts` now streams when `hazard_channel.enabled` is true
- Hazard TV selects a random playable library item and starts it at offset `0`
- when the selected item ends, Hazard TV selects another random item and continues streaming
- immediate repeats are avoided when more than one playable item exists
- Hazard TV shares the same global `streaming.max_parallel_streams` limit as the main channel
- Hazard TV remains outside XMLTV; it appears only in M3U when enabled

## Configuration

```yaml
hazard_channel:
  enabled: true
  id: "hazardtv"
  name: "Hazard TV"
  random_seed: 20260704
  avoid_immediate_repeat: true
```

## Notes

Hazard TV deliberately has no precomputed playlist and no EPG. It is a separate random channel, not a second scheduled timeline.

## Verification

```bash
pytest -q
PYTHONPATH=src python3 -m privatetv --version
```

Expected version: `PrivateTV 0.11.0`.
