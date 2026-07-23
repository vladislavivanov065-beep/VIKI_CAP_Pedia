from __future__ import annotations

from django import forms


class ArticleCreateForm(forms.Form):
    title = forms.CharField(label="Заголовок", max_length=255)
    content_source = forms.CharField(
        label="Текст статьи (Markdown)", widget=forms.Textarea, required=False
    )
    edit_summary = forms.CharField(
        label="Краткое описание изменения", max_length=500, required=False
    )


class ArticleEditForm(forms.Form):
    content_source = forms.CharField(
        label="Текст статьи (Markdown)", widget=forms.Textarea, required=False
    )
    edit_summary = forms.CharField(
        label="Краткое описание изменения", max_length=500, required=False
    )
    base_revision_id = forms.CharField(widget=forms.HiddenInput)
    article_version = forms.IntegerField(widget=forms.HiddenInput)


class ArticlePreviewForm(forms.Form):
    content_source = forms.CharField(widget=forms.Textarea, required=False)
