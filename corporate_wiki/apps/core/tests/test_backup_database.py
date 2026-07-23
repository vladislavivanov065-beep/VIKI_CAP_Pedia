import sqlite3

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.management.commands.backup_database import Command


def _make_source_db(path):
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO demo (value) VALUES ('hello')")
        conn.commit()
    finally:
        conn.close()


def test_backup_creates_a_verified_copy_with_matching_data(tmp_path):
    source = tmp_path / "source.sqlite3"
    _make_source_db(source)
    output_dir = tmp_path / "backups"

    call_command("backup_database", source=str(source), output_dir=str(output_dir))

    backups = list(output_dir.glob("db-backup-*.sqlite3"))
    assert len(backups) == 1

    conn = sqlite3.connect(str(backups[0]))
    try:
        row = conn.execute("SELECT value FROM demo").fetchone()
    finally:
        conn.close()
    assert row == ("hello",)


def test_backup_requires_an_existing_source_file(tmp_path):
    with pytest.raises(CommandError):
        call_command(
            "backup_database",
            source=str(tmp_path / "missing.sqlite3"),
            output_dir=str(tmp_path / "backups"),
        )


def test_backup_creates_output_dir_if_missing(tmp_path):
    source = tmp_path / "source.sqlite3"
    _make_source_db(source)
    output_dir = tmp_path / "nested" / "backups"

    call_command("backup_database", source=str(source), output_dir=str(output_dir))

    assert list(output_dir.glob("db-backup-*.sqlite3"))


def test_backup_deletes_file_and_raises_when_integrity_check_fails(tmp_path, monkeypatch):
    source = tmp_path / "source.sqlite3"
    _make_source_db(source)
    output_dir = tmp_path / "backups"
    monkeypatch.setattr(Command, "_integrity_check", staticmethod(lambda path: False))

    with pytest.raises(CommandError):
        call_command("backup_database", source=str(source), output_dir=str(output_dir))

    assert list(output_dir.glob("db-backup-*.sqlite3")) == []
