# Patch 02 - Local-File-Scanner und Medienkatalog

Dieser Patch implementiert den ersten produktiven Medienpfad fuer lokale Videodateien.

## Enthalten

- `FfprobeMediaProbe` fuer technische Metadaten aus `ffprobe`
- rekursiver `LocalFileScanner` fuer mehrere konfigurierte Root-Verzeichnisse
- Import lokaler Videodateien als `source_kind=local_file`
- Speicherung/Update in `media_item` und `media_asset`
- Markierung nicht mehr gefundener lokaler Dateien als `missing`
- CLI-Befehle:
  - `privatetv scan`
  - `privatetv list-media`
- Unit-Tests fuer Probe-Parsing, Scanner und Repository

## Bewusste Grenzen

- `VIDEO_TS`-Verzeichnisse werden in diesem Patch bewusst uebersprungen, damit VOB-Dateien nicht faelschlich einzeln importiert werden.
- DVD-Erkennung und Hauptfilm-Heuristik folgen in Patch 03.
- Scheduling und Streaming nutzen die importierten Medien noch nicht produktiv.

## Abnahmekriterien

- `pytest` laeuft gruen.
- `privatetv scan --config config/privatetv.example.yml` initialisiert die DB und importiert lokale Videodateien, sofern Testfixtures erzeugt wurden.
- `privatetv list-media --config config/privatetv.example.yml` zeigt importierte Medien mit Dauer, Status und URI an.
