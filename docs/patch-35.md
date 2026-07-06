# PrivateTV Patch 35 – DVD/VOB main title detection correction

This patch corrects the Patch 34 wording/behavior around DVD VOB files:

- standard DVD VOB fragments are not imported as many independent movies;
- they are imported as one logical `dvd_main_title` item by the DVD scanner;
- loose DVD rip directories (`Movie/VTS_01_1.VOB` + IFO files) are now detected, not only `Movie/VIDEO_TS/...`;
- the main title set is selected by probed duration when possible and only falls back to total VOB size when durations cannot be read;
- standalone non-DVD VOB files remain importable as local files;
- local scanner only suppresses standard VOB fragments inside an actual DVD structure.

Tests: `107 passed`.
