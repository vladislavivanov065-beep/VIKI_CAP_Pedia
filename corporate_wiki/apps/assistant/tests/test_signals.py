import pytest
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant.models import AssistantSettings

pytestmark = pytest.mark.django_db


def test_saving_an_article_schedules_a_background_sync_after_commit(
    django_capture_on_commit_callbacks, monkeypatch
):
    solo = AssistantSettings.get_solo()
    solo.local_ai_trained_at = timezone.now()
    solo.save(update_fields=["local_ai_trained_at"])

    captured = []
    monkeypatch.setattr(
        "apps.assistant.training.start_sync_article_embeddings_in_background",
        lambda article_id: captured.append(article_id),
    )
    admin = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
        article = article_services.create_article(
            title="Отпуска", content_source="Текст.", created_by=admin
        )

    assert captured
    assert all(article_id == article.pk for article_id in captured)


def test_saving_an_article_does_not_run_the_sync_before_the_transaction_commits(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "apps.assistant.training.start_sync_article_embeddings_in_background",
        lambda article_id: captured.append(article_id),
    )
    admin = UserFactory()

    article_services.create_article(title="Отпуска", content_source="Текст.", created_by=admin)

    # The test itself runs inside an uncommitted transaction, so the
    # on_commit callback registered by the signal handler never fires here
    # -- proof the sync is deferred to commit rather than run inline.
    assert captured == []
