from pathlib import Path

from privatetv.db import initialize_database


def test_initialize_database_creates_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "privatetv.sqlite3"

    initialize_database(db_path)

    assert db_path.exists()
