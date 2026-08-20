"""End-to-end wiring checks for apps.articles.visibility: the filtering
logic itself is unit-tested in test_visibility.py, this file just checks
that every read path that lists or fetches an article actually applies
it. One representative case per view -- not re-testing the filtering
rules themselves.
"""

import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.articles import services
from apps.articles.models import Article
from apps.comments.models import Comment
from apps.departments.models import Department

pytestmark = pytest.mark.django_db


def _restricted_article(*, title="Ограниченная статья"):
    admin = UserFactory()
    article = services.create_article(
        title=title, content_source="секретный текст", created_by=admin
    )
    hr = Department.objects.create(name="HR")
    article.visible_departments.add(hr)
    return article, hr


def test_article_detail_404s_for_a_user_outside_the_department(client):
    article, _hr = _restricted_article()
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.get(reverse("articles:detail", kwargs={"slug": article.slug}))

    assert response.status_code == 404


def test_article_detail_200s_for_a_user_in_the_department(client):
    article, hr = _restricted_article()
    member = UserFactory(must_change_password=False, department=hr)
    client.force_login(member)

    response = client.get(reverse("articles:detail", kwargs={"slug": article.slug}))

    assert response.status_code == 200


def test_article_detail_200s_for_staff_outside_the_department(client):
    article, _hr = _restricted_article()
    staff = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(staff)

    response = client.get(reverse("articles:detail", kwargs={"slug": article.slug}))

    assert response.status_code == 200


def test_article_edit_404s_for_a_user_outside_the_department(client):
    article, _hr = _restricted_article()
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.get(reverse("articles:edit", kwargs={"slug": article.slug}))

    assert response.status_code == 404


def test_article_history_404s_for_a_user_outside_the_department(client):
    article, _hr = _restricted_article()
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.get(reverse("articles:history", kwargs={"slug": article.slug}))

    assert response.status_code == 404


def test_article_revision_detail_404s_for_a_user_outside_the_department(client):
    article, _hr = _restricted_article()
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.get(
        reverse(
            "articles:revision_detail",
            kwargs={"slug": article.slug, "revision_number": 1},
        )
    )

    assert response.status_code == 404


def test_article_compare_404s_for_a_user_outside_the_department(client):
    article, _hr = _restricted_article()
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.get(
        reverse("articles:compare", kwargs={"slug": article.slug}), {"from": 1, "to": 1}
    )

    assert response.status_code == 404


def test_home_page_excludes_a_restricted_article_for_an_outsider(client):
    article, _hr = _restricted_article()
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.get(reverse("home"))

    assert article not in response.context["recent_articles"]


def test_home_page_includes_a_restricted_article_for_a_department_member(client):
    article, hr = _restricted_article()
    member = UserFactory(must_change_password=False, department=hr)
    client.force_login(member)

    response = client.get(reverse("home"))

    assert article in list(response.context["recent_articles"])


def test_search_excludes_a_restricted_article_for_an_outsider(client):
    article, _hr = _restricted_article(title="Уникальныйзаголовокдлятеста")
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.get(reverse("search:search"), {"q": "Уникальныйзаголовокдлятеста"})

    assert article not in [result["article"] for result in response.context["results"]]


def test_search_suggestions_exclude_a_restricted_article_for_an_outsider(client):
    article, _hr = _restricted_article(title="Уникальныйзаголовокдлятеста2")
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.get(reverse("search:suggestions"), {"q": "Уникальныйзаголовокдлятеста2"})

    titles = [item["title"] for item in response.json()["suggestions"]]
    assert article.title not in titles


def test_sidebar_list_excludes_a_restricted_article_for_an_outsider(client):
    article, _hr = _restricted_article()
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.get(reverse("articles:sidebar_list"))

    slugs = [item["slug"] for item in response.json()["articles"]]
    assert article.slug not in slugs


def test_link_suggestions_exclude_a_restricted_article_for_an_outsider(client):
    article, _hr = _restricted_article()
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.get(reverse("articles:link_suggestions"))

    slugs = [item["slug"] for item in response.json()["articles"]]
    assert article.slug not in slugs


def test_category_detail_excludes_a_restricted_article_for_an_outsider(client):
    article, _hr = _restricted_article()
    services.set_article_taxonomy(
        article_id=article.pk, category_names=["HR-документы"], tag_names=[]
    )
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)
    category = Article.objects.get(pk=article.pk).categories.get()

    response = client.get(reverse("taxonomy:category_detail", kwargs={"slug": category.slug}))

    assert article not in list(response.context["articles"])


def test_tag_detail_excludes_a_restricted_article_for_an_outsider(client):
    article, _hr = _restricted_article()
    services.set_article_taxonomy(article_id=article.pk, category_names=[], tag_names=["секретно"])
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)
    tag = Article.objects.get(pk=article.pk).tags.get()

    response = client.get(reverse("taxonomy:tag_detail", kwargs={"slug": tag.slug}))

    assert article not in list(response.context["articles"])


def test_ask_question_404s_for_a_user_outside_the_department(client):
    article, _hr = _restricted_article()
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.post(
        reverse("assistant:ask"),
        data='{"question": "вопрос", "article_slug": "%s"}' % article.slug,
        content_type="application/json",
    )

    assert response.status_code == 404


def test_comment_create_404s_for_a_user_outside_the_department(client):
    article, _hr = _restricted_article()
    outsider = UserFactory(must_change_password=False)
    client.force_login(outsider)

    response = client.post(
        reverse("comments:create", args=[article.slug]), {"text": "Комментарий."}
    )

    assert response.status_code == 404
    assert Comment.objects.count() == 0


def test_article_create_saves_the_selected_departments(client):
    admin = UserFactory(must_change_password=False)
    client.force_login(admin)
    hr = Department.objects.create(name="HR")

    response = client.post(
        reverse("articles:create"),
        {
            "title": "Новая статья",
            "content_source": "текст",
            "edit_summary": "",
            "categories": "",
            "tags": "",
            "visible_departments": [str(hr.pk)],
        },
    )

    assert response.status_code == 302
    article = Article.objects.get(title="Новая статья")
    assert list(article.visible_departments.all()) == [hr]


def test_article_edit_updates_the_selected_departments(client):
    admin = UserFactory(must_change_password=False)
    client.force_login(admin)
    article = services.create_article(title="Статья", content_source="текст", created_by=admin)
    hr = Department.objects.create(name="HR")

    response = client.post(
        reverse("articles:edit", kwargs={"slug": article.slug}),
        {
            "content_source": "текст",
            "edit_summary": "",
            "base_revision_id": str(article.current_revision_id),
            "article_version": article.version,
            "categories": "",
            "tags": "",
            "visible_departments": [str(hr.pk)],
        },
    )

    assert response.status_code == 302
    article.refresh_from_db()
    assert list(article.visible_departments.all()) == [hr]
