from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.articles.models import Article
from apps.assistant.services import sync_article_embeddings


@receiver(post_save, sender=Article)
def _sync_article_embeddings(sender, instance: Article, **kwargs) -> None:
    sync_article_embeddings(instance)
