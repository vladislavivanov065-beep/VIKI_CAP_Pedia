import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant.text_utils import article_plain_text, split_sentences

pytestmark = pytest.mark.django_db


def _article_text(content_source):
    admin = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source=content_source, created_by=admin
    )
    return article_plain_text(article)


def test_heading_does_not_merge_into_the_following_paragraph():
    text = _article_text("## Заголовок\n\nПервый абзац статьи.")

    assert split_sentences(text) == ["Заголовок", "Первый абзац статьи."]


def test_list_items_are_joined_but_kept_separate_from_surrounding_paragraphs():
    text = _article_text(
        "Что можно оплачивать:\n\n"
        "- хостинги\n- домены\n- нейросети\n\n"
        "Карты нельзя использовать в других целях."
    )

    sentences = split_sentences(text)

    assert "хостинги, домены, нейросети" in sentences
    assert "Карты нельзя использовать в других целях." in sentences
    # The list must not have swallowed the next paragraph, or vice versa.
    assert not any("Карты" in s and "нейросети" in s for s in sentences)


def test_table_rows_are_joined_but_kept_separate_from_each_other():
    text = _article_text("| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |")

    sentences = split_sentences(text)

    assert "A, B" in sentences
    assert "1, 2" in sentences
    assert "3, 4" in sentences


def test_a_paragraph_with_multiple_real_sentences_still_splits_on_punctuation():
    text = _article_text("Первое предложение. Второе предложение.")

    assert split_sentences(text) == ["Первое предложение.", "Второе предложение."]


def test_a_heading_immediately_followed_by_a_list_does_not_produce_one_giant_sentence():
    # The exact shape of the reported bug: a heading with no punctuation,
    # straight into a list with no punctuation either, used to all get
    # glued into a single "sentence" together with whatever real sentence
    # came right after it.
    text = _article_text("## Что можно оплачивать\n\n- рекламу\n- хостинги\n\nVPN оплатить нельзя.")

    sentences = split_sentences(text)

    assert "Что можно оплачивать" in sentences
    assert "рекламу, хостинги" in sentences
    assert "VPN оплатить нельзя." in sentences


def test_empty_article_returns_empty_text():
    assert _article_text("") == ""
