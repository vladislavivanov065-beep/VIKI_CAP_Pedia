from apps.articles.diffing import build_line_diff, diff_words


def test_equal_lines_are_marked_equal():
    diff = build_line_diff("a\nb\nc", "a\nb\nc")
    assert all(entry["type"] == "equal" for entry in diff)
    assert len(diff) == 3


def test_added_line_is_detected():
    diff = build_line_diff("a\nb", "a\nb\nc")
    assert diff[-1] == {"type": "added", "old": None, "new": "c"}


def test_removed_line_is_detected():
    diff = build_line_diff("a\nb\nc", "a\nc")
    removed = [entry for entry in diff if entry["type"] == "removed"]
    assert removed == [{"type": "removed", "old": "b", "new": None}]


def test_changed_line_carries_word_level_spans():
    diff = build_line_diff("Привет мир", "Привет вселенная")
    changed = [entry for entry in diff if entry["type"] == "changed"]
    assert len(changed) == 1
    assert changed[0]["old"] == "Привет мир"
    assert changed[0]["new"] == "Привет вселенная"

    old_equal_text = "".join(text for text, tag in changed[0]["old_spans"] if tag == "equal")
    old_removed_text = "".join(text for text, tag in changed[0]["old_spans"] if tag == "removed")
    new_added_text = "".join(text for text, tag in changed[0]["new_spans"] if tag == "added")
    assert "Привет" in old_equal_text
    assert "мир" in old_removed_text
    assert "вселенная" in new_added_text


def test_replace_block_with_uneven_line_counts_falls_back_to_added_removed():
    diff = build_line_diff("одна строка", "первая строка\nвторая строка")
    types = [entry["type"] for entry in diff]
    assert "changed" in types
    assert "added" in types


def test_diff_words_identical_lines_are_all_equal():
    old_spans, new_spans = diff_words("текст без изменений", "текст без изменений")
    assert all(tag == "equal" for _text, tag in old_spans)
    assert all(tag == "equal" for _text, tag in new_spans)


def test_diff_words_pure_addition():
    old_spans, new_spans = diff_words("текст", "текст добавленный")
    added_text = "".join(text for text, tag in new_spans if tag == "added")
    assert "добавленный" in added_text
    assert not any(tag == "removed" for _text, tag in old_spans)


def test_empty_texts_produce_no_entries():
    assert build_line_diff("", "") == []
