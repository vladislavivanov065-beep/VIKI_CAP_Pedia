from django.core.management.base import BaseCommand

from apps.search import fts


class Command(BaseCommand):
    help = (
        "Rebuild the SQLite FTS5 full-text search index from the current "
        "article table. Safe and idempotent to re-run; ongoing changes are "
        "kept in sync automatically via a signal, this is for the initial "
        "backfill and for manual recovery."
    )

    def handle(self, *args, **options):
        count = fts.rebuild_index()
        self.stdout.write(self.style.SUCCESS(f"Индекс поиска перестроен: {count} статей."))
