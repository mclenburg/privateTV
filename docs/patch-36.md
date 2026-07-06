# Patch 36 – DVD IFO main-title detection

Patch 36 improves DVD/VOB handling for real DVD-Video structures.

## Changed

- Adds a dependency-free DVD IFO reader for the scanner.
- Reads `VIDEO_TS.IFO` Title Search Pointer Table when available.
- Reads `VTS_XX_0.IFO` Program Chain play times.
- Selects the main title using IFO/PGC duration before falling back to ffprobe and VOB-size heuristics.
- Keeps `VTS_XX_0.VOB` / `VIDEO_TS.VOB` out of the scheduled programme because they are menu material.
- Imports `VTS_XX_1.VOB` … `VTS_XX_9.VOB` as one logical DVD main title.
- Stores the DVD main title duration from the IFO tables when available.

## Why

DVD-Video does not mark the main movie with a single explicit flag. A player infers it from the navigation tables and Program Chains. PrivateTV now follows that model more closely instead of treating VOB fragments as unrelated local movies.
