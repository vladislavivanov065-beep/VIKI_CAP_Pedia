from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.articles.models import Article
from apps.search import fts


@receiver(post_save, sender=Article)
def _sync_article_fts_index(sender, instance: Article, **kwargs) -> None:
    if instance.current_revision_id is None:
        fts.remove_article(instance.pk)
        return
    fts.index_article(instance)
