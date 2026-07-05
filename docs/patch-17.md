# Patch 17 - Human-friendly DVD titles

This patch improves title derivation for media items that are named like DVD
technical files.

## Changes

- Added a shared media title normalizer.
- DVD-standard names such as `VTS_01_2.VOB`, `VIDEO_TS.IFO`, and `VIDEO_TS`
  are no longer used as display titles.
- For such paths, the scanner walks upward and uses the first non-DVD-standard
  parent directory as the title source.
- Title normalization now replaces underscores and dots with spaces, splits
  CamelCase, and separates trailing/leading numbers from words.
- Existing future schedule entry titles are refreshed from current media item
  titles at the end of `privatetv scan`.

## Examples

- `/data/DVDs/PipiLangstrumpf_1/VTS_01_2.VOB` -> `Pipi Langstrumpf 1`
- `/data/DVDs/PipiLangstrumpf_1/VIDEO_TS/VTS_01_2.VOB` -> `Pipi Langstrumpf 1`
- `/data/Filme/Buddy&Terence/2_Himmelhunde_auf_dem_Weg_zur_Hoelle.mp4` -> `2 Himmelhunde auf dem Weg zur Hoelle`

## Validation

- `python3 -m compileall -q src tests`
- `PYTHONPATH=. pytest -q`
- Result: `69 passed`
