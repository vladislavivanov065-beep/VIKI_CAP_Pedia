import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.articles import services
from apps.articles.models import Category, Tag

pytestmark = pytest.mark.django_db


def test_set_article_taxonomy_assigns_categories_and_creates_tags():
    user = UserFactory()
    article = services.create_article(title="Статья", content_source="x", created_by=user)
    category = Category.objects.create(name="HR", slug="hr")

    services.set_article_taxonomy(
        article_id=article.pk, category_ids=[category.pk], tag_names=["отпуска", "правила"]
    )

    article.refresh_from_db()
    assert list(article.categories.all()) == [category]
    assert {t.name for t in article.tags.all()} == {"отпуска", "правила"}


def test_set_article_taxonomy_reuses_existing_tag_across_case_variants():
    user = UserFactory()
    article_a = services.create_article(title="Статья A", content_source="x", created_by=user)
    article_b = services.create_article(title="Статья B", content_source="x", created_by=user)

    services.set_article_taxonomy(article_id=article_a.pk, category_ids=[], tag_names=["Отпуска"])
    services.set_article_taxonomy(article_id=article_b.pk, category_ids=[], tag_names=["ОТПУСКА"])

    assert Tag.objects.count() == 1


def test_set_article_taxonomy_ignores_blank_tag_names():
    user = UserFactory()
    article = services.create_article(title="Статья", content_source="x", created_by=user)

    services.set_article_taxonomy(
        article_id=article.pk, category_ids=[], tag_names=["  ", "", "реальный"]
    )

    assert list(article.tags.values_list("name", flat=True)) == ["реальный"]


def test_set_article_taxonomy_replaces_previous_assignment():
    user = UserFactory()
    article = services.create_article(title="Статья", content_source="x", created_by=user)
    services.set_article_taxonomy(article_id=article.pk, category_ids=[], tag_names=["старый"])

    services.set_article_taxonomy(article_id=article.pk, category_ids=[], tag_names=["новый"])

    assert list(article.tags.values_list("name", flat=True)) == ["новый"]


def test_create_article_view_assigns_categories_and_tags(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    category = Category.objects.create(name="HR", slug="hr")

    client.post(
        reverse("articles:create"),
        {
            "title": "Новая статья",
            "content_source": "текст",
            "edit_summary": "",
            "categories": [str(category.pk)],
            "tags": "отпуска, правила",
        },
    )

    from apps.articles.models import Article

    article = Article.objects.get(title="Новая статья")
    assert list(article.categories.all()) == [category]
    assert {t.name for t in article.tags.all()} == {"отпуска", "правила"}


def test_edit_article_view_updates_tags(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = services.create_article(title="Статья", content_source="v1", created_by=user)
    services.set_article_taxonomy(article_id=article.pk, category_ids=[], tag_names=["старый"])

    client.post(
        reverse("articles:edit", kwargs={"slug": article.slug}),
        {
            "content_source": "v2",
            "edit_summary": "",
            "base_revision_id": str(article.current_revision_id),
            "article_version": article.version,
            "categories": [],
            "tags": "новый",
        },
    )

    article.refresh_from_db()
    assert list(article.tags.values_list("name", flat=True)) == ["новый"]


def test_category_list_shows_top_level_categories(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    top = Category.objects.create(name="HR", slug="hr")
    Category.objects.create(name="Отпуска", slug="otpuska", parent=top)

    response = client.get(reverse("taxonomy:category_list"))
    content = response.content.decode()
    assert response.status_code == 200
    assert "HR" in content
    assert "Отпуска" in content


def test_category_detail_lists_articles_and_subcategories(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    top = Category.objects.create(name="HR", slug="hr")
    child = Category.objects.create(name="Отпуска", slug="otpuska", parent=top)
    article = services.create_article(
        title="Статья про отпуск", content_source="x", created_by=user
    )
    article.categories.add(top)

    response = client.get(reverse("taxonomy:category_detail", kwargs={"slug": "hr"}))
    content = response.content.decode()
    assert response.status_code == 200
    assert "Статья про отпуск" in content
    assert child.name in content


def test_category_detail_excludes_archived_articles(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    category = Category.objects.create(name="HR", slug="hr")
    article = services.create_article(title="Статья", content_source="x", created_by=user)
    article.categories.add(category)
    services.archive_article(article_id=article.pk, actor=user)

    response = client.get(reverse("taxonomy:category_detail", kwargs={"slug": "hr"}))
    assert "Статья" not in response.content.decode()


def test_tag_detail_lists_articles(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    tag = Tag.objects.create(name="отпуска", slug="otpuska")
    article = services.create_article(
        title="Статья про отпуск", content_source="x", created_by=user
    )
    article.tags.add(tag)

    response = client.get(reverse("taxonomy:tag_detail", kwargs={"slug": "otpuska"}))
    content = response.content.decode()
    assert response.status_code == 200
    assert "Статья про отпуск" in content


def test_article_detail_shows_taxonomy_chips(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    category = Category.objects.create(name="HR", slug="hr")
    tag = Tag.objects.create(name="отпуска", slug="otpuska")
    article = services.create_article(title="Статья", content_source="x", created_by=user)
    article.categories.add(category)
    article.tags.add(tag)

    response = client.get(reverse("articles:detail", kwargs={"slug": article.slug}))
    content = response.content.decode()
    assert "HR" in content
    assert "#отпуска" in content
