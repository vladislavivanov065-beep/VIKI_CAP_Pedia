import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.comments.models import Comment

pytestmark = pytest.mark.django_db


def _article(**kwargs):
    admin = UserFactory()
    defaults = {"title": "Статья", "content_source": "текст", "created_by": admin}
    defaults.update(kwargs)
    return article_services.create_article(**defaults)


def _create_url(slug):
    return reverse("comments:create", args=[slug])


def test_comment_create_requires_authentication(client):
    article = _article()

    response = client.post(_create_url(article.slug), {"text": "Комментарий."})

    assert response.status_code == 302
    assert Comment.objects.count() == 0


def test_comment_create_requires_post(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _article()

    response = client.get(_create_url(article.slug))

    assert response.status_code == 405


def test_comment_create_saves_a_top_level_comment_and_redirects(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _article()

    response = client.post(_create_url(article.slug), {"text": "Мой комментарий."})

    assert response.status_code == 302
    comment = Comment.objects.get(article=article)
    assert comment.text == "Мой комментарий."
    assert comment.author == user
    assert comment.parent is None
    assert response.url == f"{reverse('articles:detail', args=[article.slug])}#comment-{comment.pk}"


def test_comment_create_saves_a_reply_with_the_given_parent(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _article()
    top_level = Comment.objects.create(article=article, author=user, text="Комментарий.")

    client.post(_create_url(article.slug), {"text": "Ответ.", "parent_id": str(top_level.pk)})

    reply = Comment.objects.get(text="Ответ.")
    assert reply.parent == top_level


def test_comment_create_flattens_a_reply_to_a_reply(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _article()
    top_level = Comment.objects.create(article=article, author=user, text="Комментарий.")
    reply = Comment.objects.create(article=article, author=user, text="Ответ.", parent=top_level)

    client.post(_create_url(article.slug), {"text": "Ответ на ответ.", "parent_id": str(reply.pk)})

    reply_to_reply = Comment.objects.get(text="Ответ на ответ.")
    assert reply_to_reply.parent == top_level


def test_comment_create_rejects_empty_text(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _article()

    response = client.post(_create_url(article.slug), {"text": "   "})

    assert response.status_code == 302
    assert response.url == reverse("articles:detail", args=[article.slug])
    assert Comment.objects.count() == 0


def test_comment_create_rejects_a_parent_from_a_different_article(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _article()
    other_article = _article(title="Другая статья")
    foreign_comment = Comment.objects.create(
        article=other_article, author=user, text="На другой статье."
    )

    response = client.post(
        _create_url(article.slug),
        {"text": "Ответ.", "parent_id": str(foreign_comment.pk)},
    )

    assert response.status_code == 302
    assert Comment.objects.filter(article=article).count() == 0


def test_comment_create_404s_for_an_unknown_article(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.post(_create_url("no-such-article"), {"text": "Комментарий."})

    assert response.status_code == 404


def test_comment_create_404s_for_an_archived_article(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _article()
    article_services.archive_article(article_id=article.pk, actor=user)

    response = client.post(_create_url(article.slug), {"text": "Комментарий."})

    assert response.status_code == 404


def test_article_detail_shows_comment_threads_in_context(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = _article()
    comment = Comment.objects.create(article=article, author=user, text="Комментарий.")

    response = client.get(reverse("articles:detail", args=[article.slug]))

    threads = response.context["comment_threads"]
    assert [t.comment for t in threads] == [comment]
