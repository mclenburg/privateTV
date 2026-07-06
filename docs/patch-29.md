# Patch 29 - Generated promos

Adds optional generated promo clips for programme continuity.

## Added

- `program_blocks.generated_promos` configuration section.
- Optional `next_up` promos, e.g. `Als nächstes: <title>`.
- Optional `coming_soon` promos with localized weekday/time text.
- Promo clips are generated with FFmpeg under `generated/promos` next to the SQLite database.
- Generated promos are cached and stored in the media catalog as `generated_promo`.
- Generated promos are tagged as `generated`, `promo`, and `filler`.

## Safety rule

Promos never target filler material. The promo generator rejects:

- local fillers
- commercials
- bumpers
- trailers
- DVD previews
- countdowns
- generated promos
- anything carrying denied promotable tags such as `filler`, `commercial`, `bumper`, `trailer`, `countdown`, or `promo`

## Compatibility

The feature is disabled by default. Existing scheduling behavior is unchanged until
`program_blocks.generated_promos.enabled` and one of its variants are enabled.
