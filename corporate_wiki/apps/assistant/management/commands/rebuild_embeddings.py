from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.articles.models import Article
from apps.assistant.services import sync_article_embeddings


class Command(BaseCommand):
    help = (
        "Recompute AI-assistant embeddings for every active article. Ongoing "
        "changes are kept in sync automatically via a signal; this is for "
        "the initial backfill and for manual recovery. Requires "
        "OPENAI_API_KEY to be set -- unlike the signal, a failure on any one "
        "article is reported instead of silently skipped (the rest still run)."
    )

    def handle(self, *args, **options):
        if not settings.OPENAI_API_KEY:
            raise CommandError(
                "OPENAI_API_KEY не задан — ИИ-ассистент не настроен, перестраивать нечего."
            )

        articles = Article.objects.filter(is_archived=False).select_related("current_revision")
        succeeded = 0
        failed = 0
        for article in articles:
            try:
                sync_article_embeddings(article, raise_on_error=True)
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f"Статья «{article.title}»: {exc}"))
            else:
                succeeded += 1

        self.stdout.write(self.style.SUCCESS(f"Обработано статей: {succeeded}."))
        if failed:
            self.stdout.write(self.style.WARNING(f"Не удалось обработать: {failed}."))
