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
