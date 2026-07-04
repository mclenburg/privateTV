# Patch 1 - Projektgeruest

## Inhalt

- Python-Projektstruktur
- CLI `privatetv`
- YAML-Konfiguration
- SQLite-Basisschema
- Domain-Modelle
- MediaSource-, ScheduleStrategy- und StreamProvider-Schnittstellen
- M3U/XMLTV-Minimalrenderer
- Health-Endpunkt
- Fixture-Erzeugungsskript
- Unit-Tests

## Abnahmekriterien

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
privatetv doctor --config config/privatetv.example.yml
privatetv init-db --config config/privatetv.example.yml
privatetv m3u --config config/privatetv.example.yml
privatetv xmltv --config config/privatetv.example.yml
```

Alle Befehle muessen erfolgreich laufen. `doctor` meldet erst dann alle Medienverzeichnisse als OK, wenn die Fixture-Verzeichnisse vorhanden sind; diese sind in diesem Patch bereits angelegt. Fuer echte Testvideos:

```bash
scripts/create_test_fixtures.sh
```
