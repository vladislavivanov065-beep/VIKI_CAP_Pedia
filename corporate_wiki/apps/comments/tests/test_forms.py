from apps.comments.forms import CommentForm


def test_comment_form_accepts_non_empty_text():
    form = CommentForm(data={"text": "Комментарий."})

    assert form.is_valid()
    assert form.cleaned_data["text"] == "Комментарий."


def test_comment_form_strips_surrounding_whitespace():
    form = CommentForm(data={"text": "  Комментарий.  "})

    assert form.is_valid()
    assert form.cleaned_data["text"] == "Комментарий."


def test_comment_form_rejects_empty_text():
    form = CommentForm(data={"text": ""})

    assert not form.is_valid()
    assert "text" in form.errors


def test_comment_form_rejects_whitespace_only_text():
    form = CommentForm(data={"text": "   "})

    assert not form.is_valid()
    assert "text" in form.errors


def test_comment_form_parent_id_is_optional():
    form = CommentForm(data={"text": "Комментарий."})

    assert form.is_valid()
    assert form.cleaned_data["parent_id"] == ""
