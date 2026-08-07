from apps.assistant import local_search


def test_find_best_sentences_matches_relevant_sentence_despite_inflection():
    text = "Отпуск оформляется за две недели. Обед начинается в полдень."

    matches = local_search.find_best_sentences(text=text, question="Когда оформлять отпуск?")

    assert matches == ["Отпуск оформляется за две недели."]


def test_find_best_sentences_ranks_more_relevant_sentence_first():
    text = (
        "Отпуск оформляется за две недели. "
        "Заявление на отпуск подаётся руководителю. "
        "Обед начинается в полдень."
    )

    matches = local_search.find_best_sentences(
        text=text, question="Как подать заявление на отпуск?", max_sentences=1
    )

    assert matches == ["Заявление на отпуск подаётся руководителю."]


def test_find_best_sentences_returns_empty_for_unrelated_question():
    text = "Отпуск оформляется за две недели."

    matches = local_search.find_best_sentences(text=text, question="Какая погода сегодня?")

    assert matches == []


def test_find_best_sentences_returns_empty_for_empty_text():
    assert local_search.find_best_sentences(text="", question="Вопрос?") == []


def test_find_best_sentences_returns_empty_for_stopword_only_question():
    text = "Отпуск оформляется за две недели."

    assert local_search.find_best_sentences(text=text, question="а и в на") == []


def test_find_best_sentences_matches_across_grammatical_case_via_lemmatization():
    # "рекламу" (accusative) in the question vs "рекламы" (genitive) in the
    # text -- same lemma "реклама", so this should match despite sharing no
    # exact word form.
    text = "Хостинги домены и оплата рекламы разрешены. Обед начинается в полдень."

    matches = local_search.find_best_sentences(text=text, question="Что можно оплачивать: рекламу?")

    assert matches == ["Хостинги домены и оплата рекламы разрешены."]


def test_pick_best_sentence_returns_the_lexically_closest_candidate():
    candidates = ["Обед начинается в полдень.", "Отпуск оформляется за две недели."]

    result = local_search.pick_best_sentence(
        sentences=candidates, question="Когда оформлять отпуск?"
    )

    assert result == "Отпуск оформляется за две недели."


def test_pick_best_sentence_returns_none_without_keyword_overlap():
    candidates = ["Обед начинается в полдень.", "Столовая на первом этаже."]

    result = local_search.pick_best_sentence(sentences=candidates, question="Когда отпуск?")

    assert result is None


def test_find_best_sentences_matches_english_words_across_inflection():
    # "billing" in the question vs "billed"/"bills" in the text -- same
    # Porter stem, so this should match despite sharing no exact word form.
    text = "Overdraft fees are billed monthly. Обед начинается в полдень."

    matches = local_search.find_best_sentences(text=text, question="How is billing calculated?")

    assert matches == ["Overdraft fees are billed monthly."]


def test_find_best_sentences_matches_within_a_mixed_russian_and_english_sentence():
    # Each word is lemmatized/stemmed by its own script -- "адрес"/"адреса"
    # (Russian) and "address"/"addresses" (English) both need to match
    # their inflected forms in the same sentence.
    text = "Логи IP address записываются автоматически. Обед начинается в полдень."

    matches = local_search.find_best_sentences(
        text=text, question="Как записываются логи IP addresses?"
    )

    assert matches == ["Логи IP address записываются автоматически."]


def test_exact_match_bonus_is_one_for_a_candidate_containing_the_questions_bin():
    # Embeddings/cross-encoders barely distinguish "493711" from "493712"
    # -- both just look like "a number" -- but that distinction matters
    # for a BIN lookup, so an exact substring match gets flagged here.
    bonuses = local_search.exact_match_bonus(
        question="Какой лимит у BIN 493711?",
        candidates=["BIN 493711 действует в Singapore.", "BIN 493712 действует в Hong Kong."],
    )

    assert bonuses == [1.0, 0.0]


def test_exact_match_bonus_is_zero_without_a_code_in_the_question():
    bonuses = local_search.exact_match_bonus(
        question="Какой лимит?", candidates=["Лимит 30000 в день.", "Другой текст."]
    )

    assert bonuses == [0.0, 0.0]


def test_exact_match_bonus_matches_alphanumeric_product_codes_too():
    bonuses = local_search.exact_match_bonus(
        question="Что такое код E0000000?",
        candidates=["Код E0000000 означает успех.", "Код C0000017 означает ошибку."],
    )

    assert bonuses == [1.0, 0.0]


def test_highlight_matches_wraps_a_word_sharing_a_lemma_with_the_question():
    result = local_search.highlight_matches(
        text="Отпуск оформляется за две недели.", question="Когда оформлять отпуск?"
    )

    assert result == "<mark>Отпуск</mark> оформляется за две недели."


def test_highlight_matches_returns_escaped_text_unchanged_without_any_match():
    result = local_search.highlight_matches(text="Обед начинается в полдень.", question="Отпуск?")

    assert result == "Обед начинается в полдень."


def test_highlight_matches_escapes_html_metacharacters():
    result = local_search.highlight_matches(text="<b>жирный</b> & «кавычки»", question="Вопрос?")

    assert "<b>" not in result
    assert result == "&lt;b&gt;жирный&lt;/b&gt; &amp; «кавычки»"


def test_highlight_matches_escapes_html_metacharacters_around_a_highlighted_word():
    result = local_search.highlight_matches(text="<b>отпуск</b> скоро", question="Когда отпуск?")

    assert result == "&lt;b&gt;<mark>отпуск</mark>&lt;/b&gt; скоро"


def test_highlight_matches_returns_escaped_text_for_a_stopword_only_question():
    result = local_search.highlight_matches(text="<i>текст</i>", question="а и в на")

    assert result == "&lt;i&gt;текст&lt;/i&gt;"
