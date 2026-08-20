import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.comments import services
from apps.comments.models import Comment

pytestmark = pytest.mark.django_db


def _article(title="Статья"):
    admin = UserFactory()
    return article_services.create_article(title=title, content_source="текст", created_by=admin)


def test_create_comment_creates_a_top_level_comment():
    article = _article()
    author = UserFactory()

    comment = services.create_comment(article=article, author=author, text="Первый комментарий.")

    assert comment.article == article
    assert comment.author == author
    assert comment.text == "Первый комментарий."
    assert comment.parent is None


def test_create_comment_attaches_a_reply_to_its_parent():
    article = _article()
    author = UserFactory()
    top_level = services.create_comment(article=article, author=author, text="Комментарий.")

    reply = services.create_comment(article=article, author=author, text="Ответ.", parent=top_level)

    assert reply.parent == top_level


def test_create_comment_flattens_a_reply_to_a_reply_onto_the_top_level_comment():
    # No more than one level of nesting: replying to a reply attaches to
    # the original top-level comment, not to the reply.
    article = _article()
    author = UserFactory()
    top_level = services.create_comment(article=article, author=author, text="Комментарий.")
    reply = services.create_comment(article=article, author=author, text="Ответ.", parent=top_level)

    reply_to_reply = services.create_comment(
        article=article, author=author, text="Ответ на ответ.", parent=reply
    )

    assert reply_to_reply.parent == top_level


def test_get_comment_threads_groups_replies_under_their_top_level_comment():
    article = _article()
    author = UserFactory()
    first = services.create_comment(article=article, author=author, text="Первый.")
    services.create_comment(article=article, author=author, text="Ответ на первый.", parent=first)
    second = services.create_comment(article=article, author=author, text="Второй.")

    threads = services.get_comment_threads(article)

    assert [t.comment for t in threads] == [first, second]
    assert [r.text for r in threads[0].replies] == ["Ответ на первый."]
    assert threads[1].replies == []


def test_get_comment_threads_orders_top_level_comments_by_creation_time():
    article = _article()
    author = UserFactory()
    first = services.create_comment(article=article, author=author, text="Первый.")
    second = services.create_comment(article=article, author=author, text="Второй.")
    third = services.create_comment(article=article, author=author, text="Третий.")

    threads = services.get_comment_threads(article)

    assert [t.comment for t in threads] == [first, second, third]


def test_get_comment_threads_orders_replies_by_creation_time():
    article = _article()
    author = UserFactory()
    top_level = services.create_comment(article=article, author=author, text="Комментарий.")
    first_reply = services.create_comment(
        article=article, author=author, text="Первый ответ.", parent=top_level
    )
    second_reply = services.create_comment(
        article=article, author=author, text="Второй ответ.", parent=top_level
    )

    threads = services.get_comment_threads(article)

    assert threads[0].replies == [first_reply, second_reply]


def test_get_comment_threads_is_scoped_to_one_article():
    article = _article()
    other_article = _article(title="Другая статья")
    author = UserFactory()
    services.create_comment(article=other_article, author=author, text="На другой статье.")

    assert services.get_comment_threads(article) == []


def test_get_comment_threads_returns_empty_list_without_any_comments():
    article = _article()

    assert services.get_comment_threads(article) == []


def test_deleting_a_top_level_comment_cascades_to_its_replies():
    article = _article()
    author = UserFactory()
    top_level = services.create_comment(article=article, author=author, text="Комментарий.")
    services.create_comment(article=article, author=author, text="Ответ.", parent=top_level)

    top_level.delete()

    assert Comment.objects.filter(article=article).count() == 0


def test_deleting_an_article_deletes_its_comments():
    article = _article()
    author = UserFactory()
    services.create_comment(article=article, author=author, text="Комментарий.")

    article.delete()

    assert Comment.objects.count() == 0
