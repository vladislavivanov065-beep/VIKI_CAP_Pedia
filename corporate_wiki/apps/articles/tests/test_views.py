import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.articles import services
from apps.articles.models import Article, ArticleRevision
from apps.attachments.tests.factories import make_txt_bytes

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


def test_link_suggestions_lists_active_article_titles(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    services.create_article(title="CardsPro", content_source="x", created_by=user)
    archived = services.create_article(title="Устаревшая", content_source="x", created_by=user)
    services.archive_article(article_id=archived.pk, actor=user)

    response = client.get(reverse("articles:link_suggestions"))

    assert response.status_code == 200
    titles = {a["title"] for a in response.json()["articles"]}
    assert "CardsPro" in titles
    assert "Устаревшая" not in titles


def test_link_suggestions_excludes_given_slug(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = services.create_article(title="CardsPro", content_source="x", created_by=user)

    response = client.get(reverse("articles:link_suggestions"), {"exclude": article.slug})

    titles = {a["title"] for a in response.json()["articles"]}
    assert "CardsPro" not in titles


def test_link_suggestions_includes_article_id_for_editor_wikilinks(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = services.create_article(title="CardsPro", content_source="x", created_by=user)

    response = client.get(reverse("articles:link_suggestions"))

    entries = {a["title"]: a["id"] for a in response.json()["articles"]}
    assert entries["CardsPro"] == str(article.pk)


def test_sidebar_list_returns_all_articles_by_default(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    services.create_article(title="CardsPro", content_source="x", created_by=user)
    services.create_article(title="Отпуск", content_source="x", created_by=user)

    response = client.get(reverse("articles:sidebar_list"))

    titles = {a["title"] for a in response.json()["articles"]}
    assert titles == {"CardsPro", "Отпуск"}


def test_sidebar_list_filters_by_query(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    services.create_article(title="CardsPro", content_source="x", created_by=user)
    services.create_article(title="Отпуск", content_source="x", created_by=user)

    response = client.get(reverse("articles:sidebar_list"), {"q": "cardspro"})

    titles = {a["title"] for a in response.json()["articles"]}
    assert titles == {"CardsPro"}


def test_anonymous_cannot_reach_sidebar_list(client):
    response = client.get(reverse("articles:sidebar_list"))
    assert response.status_code == 302


def test_archive_requires_staff(client):
    user = UserFactory(must_change_password=False, is_staff=False)
    client.force_login(user)
    article = services.create_article(title="Статья", content_source="x", created_by=user)

    response = client.post(reverse("articles:archive", kwargs={"slug": article.slug}))

    assert response.status_code == 403
    article.refresh_from_db()
    assert article.is_archived is False


def test_archive_requires_post(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)
    article = services.create_article(title="Статья", content_source="x", created_by=admin)

    response = client.get(reverse("articles:archive", kwargs={"slug": article.slug}))

    assert response.status_code == 405


def test_staff_can_archive_article(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)
    article = services.create_article(title="Статья", content_source="x", created_by=admin)

    response = client.post(reverse("articles:archive", kwargs={"slug": article.slug}))

    assert response.status_code == 302
    article.refresh_from_db()
    assert article.is_archived is True
    assert article.archived_by == admin


def test_archived_article_shows_delete_button_only_to_staff(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    regular = UserFactory(must_change_password=False, is_staff=False)
    article = services.create_article(title="Статья", content_source="x", created_by=admin)

    client.force_login(regular)
    response = client.get(reverse("articles:detail", kwargs={"slug": article.slug}))
    assert "Удалить" not in response.content.decode()

    client.force_login(admin)
    response = client.get(reverse("articles:detail", kwargs={"slug": article.slug}))
    assert "Удалить" in response.content.decode()


def test_unarchive_requires_staff(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    user = UserFactory(must_change_password=False, is_staff=False)
    article = services.create_article(title="Статья", content_source="x", created_by=admin)
    services.archive_article(article_id=article.pk, actor=admin)

    client.force_login(user)
    response = client.post(reverse("articles:unarchive", kwargs={"slug": article.slug}))

    assert response.status_code == 403
    article.refresh_from_db()
    assert article.is_archived is True


def test_staff_can_unarchive_article(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    article = services.create_article(title="Статья", content_source="x", created_by=admin)
    services.archive_article(article_id=article.pk, actor=admin)

    client.force_login(admin)
    response = client.post(reverse("articles:unarchive", kwargs={"slug": article.slug}))

    assert response.status_code == 302
    article.refresh_from_db()
    assert article.is_archived is False


def _import_upload(client, text=None):
    if text is None:
        text = "# Раздел один\nТекст раздела один.\n\n# Раздел два\nТекст раздела два."
    upload = SimpleUploadedFile("документ.txt", make_txt_bytes(text), content_type="text/plain")
    return client.post(reverse("articles:import_upload"), {"document": upload})


def test_import_upload_requires_staff(client):
    user = UserFactory(must_change_password=False, is_staff=False)
    client.force_login(user)

    response = _import_upload(client)
    assert response.status_code == 403


def test_import_upload_splits_document_and_redirects_to_review(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)

    response = _import_upload(client)
    assert response.status_code == 302
    assert response.url == reverse("articles:import_review")

    review = client.get(response.url)
    content = review.content.decode()
    assert "Раздел один" in content
    assert "Раздел два" in content


def test_import_upload_rejects_unsupported_format(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)

    upload = SimpleUploadedFile("вирус.exe", b"data", content_type="application/octet-stream")
    response = client.post(reverse("articles:import_upload"), {"document": upload})

    assert response.status_code == 200
    assert "Поддерживаются только файлы" in response.content.decode()


def test_import_review_requires_staff(client):
    user = UserFactory(must_change_password=False, is_staff=False)
    client.force_login(user)

    response = client.get(reverse("articles:import_review"))
    assert response.status_code == 403


def _first_block_id(client):
    review = client.get(reverse("articles:import_review"))
    entries = review.context["entries"]
    return entries[0]["id"]


def test_import_process_add_creates_article_and_clears_block(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)
    _import_upload(client)
    block_id = _first_block_id(client)

    response = client.post(
        reverse("articles:import_process_block", kwargs={"block_id": block_id}),
        {"action": "add", "title": "Раздел один", "content": "Текст раздела один."},
    )

    assert response.status_code == 302
    assert Article.objects.filter(title="Раздел один").exists()

    review = client.get(reverse("articles:import_review"))
    remaining_ids = [e["id"] for e in review.context["entries"]]
    assert block_id not in remaining_ids


def test_import_process_edit_add_uses_submitted_title_and_content(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)
    _import_upload(client)
    block_id = _first_block_id(client)

    client.post(
        reverse("articles:import_process_block", kwargs={"block_id": block_id}),
        {"action": "edit_add", "title": "Изменённый заголовок", "content": "Изменённый текст."},
    )

    article = Article.objects.get(title="Изменённый заголовок")
    assert article.current_revision.content_source == "Изменённый текст."


def test_import_process_skip_removes_block_without_creating_article(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)
    _import_upload(client)
    block_id = _first_block_id(client)

    client.post(
        reverse("articles:import_process_block", kwargs={"block_id": block_id}),
        {"action": "skip", "title": "Раздел один", "content": "Текст раздела один."},
    )

    assert not Article.objects.filter(title="Раздел один").exists()
    review = client.get(reverse("articles:import_review"))
    remaining_ids = [e["id"] for e in review.context["entries"]]
    assert block_id not in remaining_ids


def test_import_process_title_conflict_keeps_block_for_retry(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)
    services.create_article(title="Раздел один", content_source="уже существует", created_by=admin)
    _import_upload(client)
    block_id = _first_block_id(client)

    response = client.post(
        reverse("articles:import_process_block", kwargs={"block_id": block_id}),
        {"action": "add", "title": "Раздел один", "content": "Текст раздела один."},
        follow=True,
    )

    assert "уже существует" in response.content.decode()
    review = client.get(reverse("articles:import_review"))
    remaining_ids = [e["id"] for e in review.context["entries"]]
    assert block_id in remaining_ids


def test_import_process_unknown_block_returns_404(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)
    _import_upload(client)

    response = client.post(
        reverse("articles:import_process_block", kwargs={"block_id": "999"}),
        {"action": "skip"},
    )
    assert response.status_code == 404


def test_unarchive_with_title_conflict_shows_error_and_stays_archived(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    article = services.create_article(title="Дубликат", content_source="x", created_by=admin)
    services.archive_article(article_id=article.pk, actor=admin)
    services.create_article(title="Дубликат", content_source="y", created_by=admin)

    client.force_login(admin)
    response = client.post(
        reverse("articles:unarchive", kwargs={"slug": article.slug}), follow=True
    )

    assert "уже существует" in response.content.decode()
    article.refresh_from_db()
    assert article.is_archived is True
