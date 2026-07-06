# PrivateTV Patch 37 – DVD extras as filler candidates

Patch 37 extends DVD scanning after the IFO-based main-title work:

- the DVD main title remains one logical `dvd_main_title` item;
- VTS menu VOBs (`VTS_XX_0.VOB`) are still excluded;
- short non-main VTS groups are imported as `dvd_extra_filler` items;
- DVD extra fillers get automatic tags: `filler`, `dvd_extra`, `dvd`;
- the scan summary counts `dvd_extra_filler` as filler;
- extras are conservative VTS-level imports, because PrivateTV cannot yet address arbitrary PGC/cell chains independently inside one VTS.

Conservative duration rule for DVD extra fillers:

- minimum: 15 seconds
- maximum: 600 seconds

Tests: `111 passed`.
