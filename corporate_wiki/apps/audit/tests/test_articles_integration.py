import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


def test_create_article_is_audited():
    user = UserFactory()
    article = services.create_article(
        title="Аудит статьи", content_source="x", created_by=user, user_agent="ua-create"
    )

    entry = AuditLog.objects.get(action="article.created", object_id=article.pk)
    assert entry.actor == user
    assert entry.user_agent == "ua-create"
    assert entry.metadata["slug"] == article.slug


def test_update_article_is_audited():
    user = UserFactory()
    article = services.create_article(title="Статья", content_source="v1", created_by=user)

    services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="v2",
        edited_by=user,
        user_agent="ua-edit",
    )

    entry = AuditLog.objects.get(action="article.edited", object_id=article.pk)
    assert entry.user_agent == "ua-edit"


def test_rename_archive_restore_are_audited():
    admin = UserFactory(is_staff=True, is_superuser=True)
    article = services.create_article(title="Старое имя", content_source="x", created_by=admin)

    services.rename_article(
        article_id=article.pk,
        new_title="Новое имя",
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        edited_by=admin,
    )
    assert AuditLog.objects.filter(action="article.renamed", object_id=article.pk).exists()

    services.archive_article(article_id=article.pk, actor=admin)
    assert AuditLog.objects.filter(action="article.archived", object_id=article.pk).exists()

    services.restore_article(article_id=article.pk, actor=admin)
    assert AuditLog.objects.filter(action="article.restored", object_id=article.pk).exists()


def test_restore_revision_is_audited():
    user = UserFactory()
    article = services.create_article(title="Версии", content_source="v1", created_by=user)
    article = services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="v2",
        edited_by=user,
    )

    services.restore_revision(
        article_id=article.pk,
        revision_number=1,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        actor=user,
    )

    assert AuditLog.objects.filter(action="revision.restored", object_id=article.pk).exists()


def test_article_created_via_view_is_audited_with_user_agent(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    from django.urls import reverse

    response = client.post(
        reverse("articles:create"),
        {"title": "Через форму", "content_source": "текст", "edit_summary": ""},
        HTTP_USER_AGENT="editor-browser/9.0",
    )
    assert response.status_code == 302

    entry = AuditLog.objects.filter(action="article.created", actor=user).latest("created_at")
    assert entry.user_agent == "editor-browser/9.0"


def test_admin_archive_and_restore_actions_work_and_are_audited(client):
    admin = UserFactory(is_staff=True, is_superuser=True, must_change_password=False)
    client.force_login(admin)
    article = services.create_article(title="Через админку", content_source="x", created_by=admin)

    from django.urls import reverse

    response = client.post(
        reverse("admin:articles_article_changelist"),
        {"action": "archive_selected", "_selected_action": [str(article.pk)]},
    )
    assert response.status_code in (200, 302)
    article.refresh_from_db()
    assert article.is_archived is True
    assert AuditLog.objects.filter(action="article.archived", object_id=article.pk).exists()

    response = client.post(
        reverse("admin:articles_article_changelist"),
        {"action": "restore_selected", "_selected_action": [str(article.pk)]},
    )
    assert response.status_code in (200, 302)
    article.refresh_from_db()
    assert article.is_archived is False
    assert AuditLog.objects.filter(action="article.restored", object_id=article.pk).exists()
