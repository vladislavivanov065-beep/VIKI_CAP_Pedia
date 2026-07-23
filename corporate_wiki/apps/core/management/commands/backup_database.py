"""Consistent SQLite backups (section 25, Этап 11.6).

Uses SQLite's own online backup API rather than copying the database
file on disk — a plain file copy taken while something is writing can
land mid-transaction and produce a corrupt snapshot. The backup API
copies page-by-page under SQLite's own locking, so it is safe to run
while the application is serving requests.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Create a consistent copy of the SQLite database via the online "
        "backup API and verify its integrity. Safe to run while the "
        "application is serving requests."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=None,
            help="Database file to back up (default: the configured SQLITE_PATH).",
        )
        parser.add_argument(
            "--output-dir",
            default=None,
            help="Directory to write the backup into (default: settings.BACKUP_DIR).",
        )

    def handle(self, *args, **options):
        source_path = Path(options["source"] or settings.DATABASES["default"]["NAME"])
        if not source_path.exists():
            raise CommandError(f"База данных не найдена: {source_path}")

        output_dir = Path(options["output_dir"] or settings.BACKUP_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        dest_path = output_dir / f"db-backup-{timestamp}.sqlite3"

        self._run_backup(source_path, dest_path)

        if not self._integrity_check(dest_path):
            dest_path.unlink(missing_ok=True)
            raise CommandError("Резервная копия не прошла проверку целостности и была удалена.")

        size_kb = dest_path.stat().st_size / 1024
        self.stdout.write(
            self.style.SUCCESS(
                f"Резервная копия создана и проверена: {dest_path} ({size_kb:.0f} КБ)."
            )
        )

    @staticmethod
    def _run_backup(source_path: Path, dest_path: Path) -> None:
        source_conn = sqlite3.connect(str(source_path))
        try:
            dest_conn = sqlite3.connect(str(dest_path))
            try:
                source_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            source_conn.close()

    @staticmethod
    def _integrity_check(path: Path) -> bool:
        conn = sqlite3.connect(str(path))
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
        return result is not None and result[0] == "ok"
