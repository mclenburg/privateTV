# Patch 41 – Correct DVD PGC_PLAY_TIME offset

Fixes DVD IFO duration parsing for real authored DVDs where the VTS_PGCITI
entry points at a descriptor with two reserved bytes before the PGC header.
PrivateTV previously read PGC_PLAY_TIME at `pgc + 2`, which interpreted the
program and cell counts as hour/minute values. This produced durations such as
04:05:00 or 05:05:00 for children's DVDs.

The parser now reads:

- program count at `pgc + 2`
- cell count at `pgc + 3`
- `PGC_PLAY_TIME` at `pgc + 4 .. pgc + 7`
- cell playback offset at `pgc + 0x14 .. pgc + 0x15`

Existing sanity checks from patch 40 remain in place.
