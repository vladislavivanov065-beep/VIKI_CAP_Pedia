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
