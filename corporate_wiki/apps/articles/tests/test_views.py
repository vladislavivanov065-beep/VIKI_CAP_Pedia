import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.articles import services
from apps.articles.models import Article, ArticleRevision

pytestmark = pytest.mark.django_db


def test_anonymous_cannot_create_or_view_articles(client):
    user = UserFactory()
    article = services.create_article(title="Секретная", content_source="x", created_by=user)

    response = client.get(reverse("articles:create"))
    assert response.status_code == 302

    response = client.get(reverse("articles:detail", kwargs={"slug": article.slug}))
    assert response.status_code == 302


def test_create_article_view_creates_and_redirects(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.post(
        reverse("articles:create"),
        {"title": "Новая статья", "content_source": "## Раздел\nтекст", "edit_summary": ""},
    )

    article = Article.objects.get(title="Новая статья")
    assert response.status_code == 302
    assert response.url == reverse("articles:detail", kwargs={"slug": article.slug})
    assert article.current_revision.content_html


def test_create_article_prefills_title_from_query_param(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("articles:create"), {"title": "Из красной ссылки"})
    assert response.status_code == 200
    assert 'value="Из красной ссылки"' in response.content.decode()


def test_create_article_rejects_duplicate_title(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    services.create_article(title="Дубликат", content_source="a", created_by=user)

    response = client.post(
        reverse("articles:create"),
        {"title": "дубликат", "content_source": "b", "edit_summary": ""},
    )

    assert response.status_code == 200
    assert "уже существует" in response.content.decode()


def test_article_detail_renders_content_and_toc(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = services.create_article(
        title="Статья с разделами",
        content_source="## Введение\nтекст\n## Заключение\nтекст",
        created_by=user,
    )

    response = client.get(reverse("articles:detail", kwargs={"slug": article.slug}))
    content = response.content.decode()

    assert response.status_code == 200
    assert "<h2" in content
    assert 'href="#введение"' in content


def test_archived_article_shows_warning_banner(client):
    admin = UserFactory(must_change_password=False, is_staff=True, is_superuser=True)
    client.force_login(admin)
    article = services.create_article(title="Архивная статья", content_source="x", created_by=admin)
    services.archive_article(article_id=article.pk, actor=admin)

    response = client.get(reverse("articles:detail", kwargs={"slug": article.slug}))
    assert response.status_code == 200
    assert "архивирована" in response.content.decode()


def test_edit_article_saves_new_revision(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = services.create_article(title="Правим", content_source="v1", created_by=user)

    response = client.post(
        reverse("articles:edit", kwargs={"slug": article.slug}),
        {
            "content_source": "v2",
            "edit_summary": "правка",
            "base_revision_id": str(article.current_revision_id),
            "article_version": article.version,
        },
    )

    assert response.status_code == 302
    article.refresh_from_db()
    assert article.version == 2
    assert article.current_revision.content_source == "v2"


def test_edit_article_conflict_shows_both_versions_without_overwriting(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = services.create_article(title="Гонка", content_source="v1", created_by=user)
    stale_revision_id = article.current_revision_id
    stale_version = article.version

    services.update_article(
        article_id=article.pk,
        base_revision_id=stale_revision_id,
        article_version=stale_version,
        content_source="v2 сохранено кем-то другим",
        edited_by=user,
    )

    response = client.post(
        reverse("articles:edit", kwargs={"slug": article.slug}),
        {
            "content_source": "мой конфликтующий текст",
            "edit_summary": "",
            "base_revision_id": str(stale_revision_id),
            "article_version": stale_version,
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "изменить другой пользователь" in content
    assert "v2 сохранено кем-то другим" in content
    assert "мой конфликтующий текст" in content

    article.refresh_from_db()
    assert article.current_revision.content_source == "v2 сохранено кем-то другим"
    assert ArticleRevision.objects.filter(article=article).count() == 2


def test_rename_redirect_old_slug_reaches_new_article(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = services.create_article(
        title="Старое имя статьи", content_source="x", created_by=user
    )
    old_slug = article.slug

    renamed = services.rename_article(
        article_id=article.pk,
        new_title="Новое имя статьи",
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        edited_by=user,
    )

    response = client.get(reverse("articles:detail", kwargs={"slug": old_slug}))
    assert response.status_code == 301
    assert response.url == reverse("articles:detail", kwargs={"slug": renamed.slug})

    followed = client.get(response.url)
    assert followed.status_code == 200
    assert "Новое имя статьи" in followed.content.decode()


def test_preview_endpoint_returns_rendered_html(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.post(reverse("articles:preview"), {"content_source": "**жирный текст**"})

    assert response.status_code == 200
    data = response.json()
    assert "<strong>жирный текст</strong>" in data["content_html"]


def test_preview_endpoint_sanitizes_script_tags(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.post(
        reverse("articles:preview"), {"content_source": "<script>alert(1)</script>Безопасно"}
    )

    data = response.json()
    assert "<script" not in data["content_html"]
    assert "Безопасно" in data["content_html"]


def test_preview_endpoint_rejects_get(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("articles:preview"))
    assert response.status_code == 405
