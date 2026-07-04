# Patch 03 - DVD VIDEO_TS detection

## Scope

Patch 03 adds DVD structure scanning on top of the local file scanner from Patch 02.

Implemented:

- `DvdStructureScanner`
- Detection of `VIDEO_TS` directories below all configured media roots
- Grouping of `VTS_XX_N.VOB` files by title set
- Main-title heuristic using the largest title set
- Import of a DVD structure as one logical `media_item`
- Storage of VOB parts as ordered `media_asset` rows
- Combined scan persistence for `local_file` and `dvd_structure`
- English, public-project oriented `README.md`

## Deliberate limitations

- DVD menus are ignored.
- `VTS_XX_0.VOB` is treated as menu/navigation material and skipped.
- The first audio stream is still accepted implicitly; language selection comes later.
- Complex authored DVDs and multi-episode discs may need manual handling in a later release.
- VOB concat streaming is not implemented yet; that remains part of the streaming/spike patches.

## Verification

Run:

```bash
pytest -q
scripts/create_test_fixtures.sh
privatetv scan --config config/privatetv.example.yml
privatetv list-media --config config/privatetv.example.yml
```

Expected result:

- local fixture MP4 files are imported as `local_file`
- the synthetic `VIDEO_TS` structure is imported once as `dvd_structure`
- individual VOB files inside `VIDEO_TS` are not imported as separate movies
