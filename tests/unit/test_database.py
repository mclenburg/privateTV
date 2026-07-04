from pathlib import Path

from privatetv.db import connect_database, initialize_database


def test_initialize_database_creates_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "privatetv.sqlite3"

    initialize_database(db_path)

    assert db_path.exists()


def test_initialize_database_does_not_create_unused_runtime_stream_table(tmp_path: Path) -> None:
    db_path = tmp_path / "privatetv.sqlite3"

    initialize_database(db_path)

    with connect_database(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'runtime_stream'"
        ).fetchall()
    assert rows == []
