import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant.text_utils import article_plain_text, split_blocks, split_sentences

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


def test_list_merges_into_its_introducing_paragraph_but_not_the_next_one():
    text = _article_text(
        "Что можно оплачивать:\n\n"
        "- хостинги\n- домены\n- нейросети\n\n"
        "Карты нельзя использовать в других целях."
    )

    sentences = split_sentences(text)

    assert "Что можно оплачивать: хостинги, домены, нейросети" in sentences
    assert "Карты нельзя использовать в других целях." in sentences


def test_table_rows_are_joined_but_kept_separate_from_each_other():
    text = _article_text("| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |")

    sentences = split_sentences(text)

    assert "A, B" in sentences
    assert "1, 2" in sentences
    assert "3, 4" in sentences


def test_a_paragraph_with_multiple_real_sentences_still_splits_on_punctuation():
    text = _article_text("Первое предложение. Второе предложение.")

    assert split_sentences(text) == ["Первое предложение.", "Второе предложение."]


def test_a_heading_introducing_a_list_merges_with_it_but_not_the_next_sentence():
    # The exact shape of the reported bug: a heading with no punctuation,
    # straight into a list, used to all get glued into a single "sentence"
    # together with whatever real sentence came right after it. Now the
    # heading merges *only* with the list it introduces.
    text = _article_text("## Что можно оплачивать\n\n- рекламу\n- хостинги\n\nVPN оплатить нельзя.")

    sentences = split_sentences(text)

    assert "Что можно оплачивать рекламу, хостинги" in sentences
    assert "VPN оплатить нельзя." in sentences


def test_empty_article_returns_empty_text():
    assert _article_text("") == ""


def test_split_blocks_keeps_a_multi_sentence_paragraph_as_one_block():
    # Unlike split_sentences, split_blocks doesn't split on "." within a
    # block -- see apps.assistant.training, which indexes by block, not
    # by grammatical sentence.
    text = _article_text("Первое предложение. Второе предложение.")

    assert split_blocks(text) == ["Первое предложение. Второе предложение."]


def test_split_blocks_keeps_an_intro_sentence_together_with_its_list():
    text = _article_text(
        "Случаи, при которых возможен овердрафт.\n\n"
        "- Недостаточно средств при оплате\n"
        "- Комиссия списана сверх остатка\n\n"
        "Другой, не связанный с этим абзац."
    )

    blocks = split_blocks(text)

    assert (
        "Случаи, при которых возможен овердрафт. "
        "Недостаточно средств при оплате, Комиссия списана сверх остатка"
    ) in blocks
    assert "Другой, не связанный с этим абзац." in blocks


def test_split_blocks_keeps_unrelated_paragraphs_separate():
    text = _article_text("Первый абзац.\n\nВторой, никак не связанный абзац.")

    assert split_blocks(text) == ["Первый абзац.", "Второй, никак не связанный абзац."]
