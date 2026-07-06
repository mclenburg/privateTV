# Patch 38 - DVD PGC/cell extras as generated fillers

Patch 38 extends the DVD scanner beyond title-set level extras.

New behavior:

- reads individual PGC entries from `VTS_XX_0.IFO`
- reads PGC cell playback sector ranges where available
- excludes the selected main PGC
- extracts short non-main PGCs as real generated MP4 filler clips
- stores generated clips under `generated/dvd-extras` next to the SQLite database
- imports the generated clips as `dvd_pgc_extra_filler`
- automatic tags include `filler`, `dvd`, and `dvd_extra`

The feature remains conservative:

- only PGCs with duration between 15 and 600 seconds are considered fillers
- PGCs without cell sector ranges are not extracted
- title-set-level extras from Patch 37 still cover simple DVDs where bonus clips live in their own VTS
- menu VOBs remain excluded

This makes it possible to use short DVD bonus material inside the same VTS as filler without exposing raw VOB fragments as normal movies.
