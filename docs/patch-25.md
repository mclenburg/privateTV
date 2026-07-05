# Patch 25 - Time blocks

Patch 25 adds optional daily time blocks on top of anchors, tags, fillers, and generated countdowns.

## Added

- `program_blocks.blocks` for daily time windows such as `06:00` to `08:30`.
- Block fields:
  - `enabled`
  - `start`
  - `duration` (`HH:MM` or `HH:MM:SS`)
  - `title`
  - `allowed_tags`
  - `denied_tags`
  - `tag_match` (`any` or `all`)
  - `if_empty` (`continue_current_mode` or `skip_block`)
- Scheduler preference for media matching the active block.
- Scheduler lookahead to avoid starting long non-block items shortly before a block when a shorter item can fit.
- Validation for block start, duration, tag match mode, and fallback mode.

## Compatibility

Blocks are disabled by default. Without enabled `program_blocks.blocks`, existing scheduling behavior is unchanged.

## Example

```yaml
program_blocks:
  enabled: true
  blocks:
    - enabled: true
      start: "06:00"
      duration: "02:30:00"
      title: "PrivateTV Kinderzeit"
      allowed_tags:
        - "kids"
      denied_tags:
        - "nicht_fuer_kinder"
      tag_match: "any"
      if_empty: "continue_current_mode"
```

## Design note

Blocks are intentionally tag-light. Use broad tags so every block has enough material. The tag system supports precise labels, but scheduling gets brittle when slots require overly narrow combinations.
