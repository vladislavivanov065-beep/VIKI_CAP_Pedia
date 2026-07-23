import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.articles import services
from apps.articles.models import ArticleRevision

pytestmark = pytest.mark.django_db


def _make_article_with_revisions(user, count=3):
    article = services.create_article(title="История версий", content_source="v1", created_by=user)
    for i in range(2, count + 1):
        article = services.update_article(
            article_id=article.pk,
            base_revision_id=article.current_revision_id,
            article_version=article.version,
            content_source=f"v{i}",
            edited_by=user,
            edit_summary=f"правка {i}",
        )
    return article


def test_history_page_lists_all_revisions_newest_first(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _make_article_with_revisions(user, count=3)

    response = client.get(reverse("articles:history", kwargs={"slug": article.slug}))
    content = response.content.decode()

    assert response.status_code == 200
    assert content.index("№3") < content.index("№2") < content.index("№1")


def test_history_username_hidden_from_regular_users_but_shown_to_staff(client):
    author = UserFactory(must_change_password=False, username="author")
    article = services.create_article(title="Статья", content_source="x", created_by=author)

    regular = UserFactory(must_change_password=False)
    client.force_login(regular)
    response = client.get(reverse("articles:history", kwargs={"slug": article.slug}))
    assert "author" not in response.content.decode()

    client.logout()
    staff = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(staff)
    response = client.get(reverse("articles:history", kwargs={"slug": article.slug}))
    assert "author" in response.content.decode()


def test_history_pagination(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _make_article_with_revisions(user, count=25)

    page1 = client.get(reverse("articles:history", kwargs={"slug": article.slug}))
    assert page1.status_code == 200
    assert "?page=2" in page1.content.decode()

    page2 = client.get(reverse("articles:history", kwargs={"slug": article.slug}), {"page": 2})
    assert page2.status_code == 200
    assert ArticleRevision.objects.filter(article=article).count() == 25


def test_revision_detail_shows_warning_for_old_version(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _make_article_with_revisions(user, count=2)

    response = client.get(
        reverse("articles:revision_detail", kwargs={"slug": article.slug, "revision_number": 1})
    )
    content = response.content.decode()
    assert "Это не текущая версия статьи" in content
    assert "Восстановить эту версию" in content


def test_revision_detail_no_warning_for_current_version(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _make_article_with_revisions(user, count=2)

    response = client.get(
        reverse("articles:revision_detail", kwargs={"slug": article.slug, "revision_number": 2})
    )
    content = response.content.decode()
    assert "Это не текущая версия статьи" not in content
    assert "Восстановить эту версию" not in content


def test_revision_detail_navigation_links(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _make_article_with_revisions(user, count=3)

    response = client.get(
        reverse("articles:revision_detail", kwargs={"slug": article.slug, "revision_number": 2})
    )
    content = response.content.decode()
    assert "Предыдущая версия" in content
    assert "Следующая версия" in content


def test_compare_shows_added_and_removed_lines(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = services.create_article(
        title="Сравниваемая", content_source="строка A\nстрока B", created_by=user
    )
    article = services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="строка A\nстрока C",
        edited_by=user,
    )

    response = client.get(
        reverse("articles:compare", kwargs={"slug": article.slug}), {"from": 1, "to": 2}
    )
    content = response.content.decode()
    assert response.status_code == 200
    assert "строка A" in content


def test_compare_diff_output_is_html_escaped(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = services.create_article(
        title="XSS в диффе", content_source="безопасно", created_by=user
    )
    article = services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="<script>alert(1)</script>",
        edited_by=user,
    )

    response = client.get(
        reverse("articles:compare", kwargs={"slug": article.slug}), {"from": 1, "to": 2}
    )
    content = response.content.decode()
    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;" in content


def test_compare_unified_mode(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = services.create_article(title="Юнифайд", content_source="старое", created_by=user)
    article = services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="новое",
        edited_by=user,
    )

    response = client.get(
        reverse("articles:compare", kwargs={"slug": article.slug}),
        {"from": 1, "to": 2, "view": "unified"},
    )
    assert response.status_code == 200
    assert "diff-unified" in response.content.decode()


def test_compare_accepts_reversed_from_to(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = services.create_article(title="Обратный порядок", content_source="a", created_by=user)
    article = services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="b",
        edited_by=user,
    )

    response = client.get(
        reverse("articles:compare", kwargs={"slug": article.slug}), {"from": 2, "to": 1}
    )
    assert response.status_code == 200


def test_restore_revision_via_view_creates_new_current_revision(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _make_article_with_revisions(user, count=3)

    response = client.post(
        reverse("articles:restore", kwargs={"slug": article.slug, "revision_number": 1}),
        {"base_revision_id": str(article.current_revision_id), "article_version": article.version},
    )

    assert response.status_code == 302
    article.refresh_from_db()
    assert article.version == 4
    assert article.current_revision.content_source == "v1"
    assert article.current_revision.restored_from.revision_number == 1


def test_restore_requires_post(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _make_article_with_revisions(user, count=2)

    response = client.get(
        reverse("articles:restore", kwargs={"slug": article.slug, "revision_number": 1})
    )
    assert response.status_code == 405


def test_anonymous_cannot_view_history_or_revisions(client):
    user = UserFactory()
    article = _make_article_with_revisions(user, count=2)

    assert client.get(reverse("articles:history", kwargs={"slug": article.slug})).status_code == 302
    assert (
        client.get(
            reverse("articles:revision_detail", kwargs={"slug": article.slug, "revision_number": 1})
        ).status_code
        == 302
    )
    assert client.get(reverse("articles:compare", kwargs={"slug": article.slug})).status_code == 302


def test_view_source_shows_raw_markdown_not_rendered_html(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    from apps.articles import services as article_services

    article = article_services.create_article(
        title="Исходный код", content_source="## Заголовок\n**жирный**", created_by=user
    )

    response = client.get(
        reverse("articles:detail", kwargs={"slug": article.slug}), {"view": "source"}
    )
    content = response.content.decode()
    assert "## Заголовок" in content
    assert "**жирный**" in content
    assert "<strong>" not in content


def test_restore_conflict_redirects_back_with_message(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _make_article_with_revisions(user, count=2)
    stale_revision_id = article.current_revision_id
    stale_version = article.version

    services.update_article(
        article_id=article.pk,
        base_revision_id=stale_revision_id,
        article_version=stale_version,
        content_source="кто-то ещё сохранил",
        edited_by=user,
    )

    response = client.post(
        reverse("articles:restore", kwargs={"slug": article.slug, "revision_number": 1}),
        {"base_revision_id": str(stale_revision_id), "article_version": stale_version},
    )

    assert response.status_code == 302
    assert response.url == reverse(
        "articles:revision_detail", kwargs={"slug": article.slug, "revision_number": 1}
    )
