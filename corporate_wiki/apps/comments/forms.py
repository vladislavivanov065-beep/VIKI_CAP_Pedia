from __future__ import annotations

from django import forms

# A generous cap, not a real limit on discussion -- just a guard against a
# pathologically large paste (same spirit as apps.assistant.services'
# _MAX_ARTICLE_CHARS).
_MAX_COMMENT_LENGTH = 5000


class CommentForm(forms.Form):
    text = forms.CharField(
        label="Комментарий", widget=forms.Textarea, max_length=_MAX_COMMENT_LENGTH
    )
    # Empty for a top-level comment; the id of the comment being replied
    # to otherwise. Resolved and validated against the article in
    # apps.comments.views.comment_create -- not trusted as-is.
    parent_id = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_text(self) -> str:
        text = self.cleaned_data["text"].strip()
        if not text:
            raise forms.ValidationError("Комментарий не может быть пустым.")
        return text
