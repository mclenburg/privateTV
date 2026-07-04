# Patch 04 - Schedule Builder

This patch adds the first productive scheduling implementation.

## Added

- `ScheduleBuilder` for continuous channel timelines
- `shuffle_no_repeat` schedule strategy
- `alphabetical` debug strategy
- schedule repository for storing and reading `schedule_entry` rows
- XMLTV rendering from stored schedule entries
- CLI commands:
  - `privatetv schedule`
  - `privatetv current`
- project README converted to public, English project documentation
- license metadata corrected to use the repository `LICENSE` file

## Acceptance criteria

- Unit tests for schedule strategy ordering are green.
- Unit tests prove that the builder creates a continuous 5-day-like timeline without gaps.
- XMLTV output uses the timezone offset of each programme timestamp instead of a hard-coded offset.
- `privatetv schedule` can create schedule entries from scanned media.
- `privatetv xmltv` emits programme entries after scheduling.

## Known limitations

- The schedule is append-only when an existing future schedule is present.
- Manual programme editing is not supported yet.
- Time-block scheduling is intentionally reserved for a later release.
