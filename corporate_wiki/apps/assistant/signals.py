"""Keeps the local AI's sentence embeddings for an article in sync with
its content on every save (create, edit, rename, archive/restore, revision
restore all go through Article.save()) -- mirrors apps.search's FTS sync
signal. The actual work happens in a background thread, and only once the
outer transaction has committed (transaction.on_commit), so a save
request never blocks on loading an ML model and never races a reader that
hasn't seen the new revision yet.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.articles.models import Article
from apps.assistant import training


@receiver(post_save, sender=Article)
def _sync_article_embeddings(sender, instance: Article, **kwargs) -> None:
    transaction.on_commit(lambda: training.start_sync_article_embeddings_in_background(instance.pk))
