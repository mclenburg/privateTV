# Patch 26: Make `if_empty: skip_block` effective

This patch fixes the time-block fallback semantics introduced with program blocks.

## Fixed

- `program_blocks.blocks[].if_empty: skip_block` is no longer a no-op.
- When a time block is active and no normal media item matches its tag rules, `skip_block` leaves the block window empty instead of scheduling unrelated fallback media inside it.
- `continue_current_mode` keeps the previous fallback behavior and continues normal rotation when a block has no matching media.

## Notes

`skip_block` can intentionally create a gap in the generated schedule. Use it only for blocks where playing unrelated content would be worse than having no scheduled programme for that time window.

## Tests

- Added regression coverage for `skip_block`.
- Added coverage that `continue_current_mode` remains unchanged.
