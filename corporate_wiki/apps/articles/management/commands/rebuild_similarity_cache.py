from django.core.management.base import BaseCommand
from django.db import transaction

from apps.articles.models import ArticleSimilarity
from apps.articles.similarity import compute_all_similarities


class Command(BaseCommand):
    help = (
        "Recompute and cache each article's top similar articles (TF-IDF "
        "cosine similarity), instead of computing it live on every page "
        "view. Safe and idempotent to re-run periodically (e.g. via cron); "
        "new articles still get a live recommendation until the next run."
    )

    def handle(self, *args, **options):
        results = compute_all_similarities()

        with transaction.atomic():
            ArticleSimilarity.objects.all().delete()
            rows = [
                ArticleSimilarity(
                    article_id=article_id, related_article_id=related_id, score=score, rank=rank
                )
                for article_id, related in results.items()
                for rank, (related_id, score) in enumerate(related, start=1)
            ]
            ArticleSimilarity.objects.bulk_create(rows)

        self.stdout.write(self.style.SUCCESS(f"Кэш похожих статей обновлён: {len(rows)} записей."))
