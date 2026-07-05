# Patch 19 - Generated countdown filler

Patch 19 activates the first optional program-block behavior without changing the default scheduler.

## Behavior

When all of the following are configured:

- `program_blocks.enabled: true`
- an enabled anchor, for example `time: "20:15"`
- `program_blocks.generated_countdown.enabled: true`

PrivateTV ensures a reusable 60-second generated countdown clip exists below the configured database directory:

```text
<database-dir>/generated/countdowns/countdown_60.mp4
```

If the running schedule reaches an enabled anchor with a remaining gap of 1 to 60 seconds, the scheduler inserts the matching suffix of the generated countdown so that the next normal programme starts exactly at the anchor time.

Gaps longer than 60 seconds are intentionally not filled by countdown. In that case, the existing continuous film-after-film scheduling behavior is preserved until local filler support is added.

## Safety

- Default remains `program_blocks.enabled: false`.
- Countdown duration is still hard-limited to 60 seconds by configuration validation.
- Generated clips use source kind `generated`, so normal media scans do not mark them missing.

## Tests

```text
75 passed
```
