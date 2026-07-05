# Patch 20 - Local filler clips before anchors

Patch 20 turns the optional filler scaffolding into scheduler behavior while keeping the legacy mode as the default.

## Changes

- Adds `program_blocks.fillers.max_duration_seconds` with validation.
- Scans configured `program_blocks.fillers.directories` as local `media_type: filler` clips when program blocks and fillers are enabled.
- Keeps filler clips out of the normal film rotation.
- Uses filler clips only when the next normal item would overrun an enabled anchor.
- Keeps the generated countdown as the final fine adjustment and still limits it to 60 seconds.
- Preserves film-after-film scheduling when program blocks are disabled or when no suitable filler is available.

## Example

```yaml
program_blocks:
  enabled: true
  anchors:
    - enabled: true
      time: "20:15"
      title: "Der 20:15 Film"
  fillers:
    enabled: true
    directories:
      - "/data/PrivateTV/Filler"
    max_duration_seconds: 900
    if_no_filler: "continue_current_mode"
  generated_countdown:
    enabled: true
    max_duration_seconds: 60
    title: "Gleich geht's weiter"
```
