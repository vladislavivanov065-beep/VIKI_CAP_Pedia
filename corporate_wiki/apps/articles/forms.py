from __future__ import annotations

from django import forms

from apps.articles.models import Category


class ArticleCreateForm(forms.Form):
    title = forms.CharField(label="Заголовок", max_length=255)
    content_source = forms.CharField(
        label="Текст статьи (Markdown)", widget=forms.Textarea, required=False
    )
    edit_summary = forms.CharField(
        label="Краткое описание изменения", max_length=500, required=False
    )
    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.all(), required=False, label="Категории"
    )
    tags = forms.CharField(
        label="Теги",
        required=False,
        help_text="Через запятую, например: hr, отпуска, регламенты",
    )

    def clean_tags(self) -> list[str]:
        return [name.strip() for name in self.cleaned_data["tags"].split(",") if name.strip()]


class ArticleEditForm(forms.Form):
    content_source = forms.CharField(
        label="Текст статьи (Markdown)", widget=forms.Textarea, required=False
    )
    edit_summary = forms.CharField(
        label="Краткое описание изменения", max_length=500, required=False
    )
    base_revision_id = forms.CharField(widget=forms.HiddenInput)
    article_version = forms.IntegerField(widget=forms.HiddenInput)
    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.all(), required=False, label="Категории"
    )
    tags = forms.CharField(
        label="Теги",
        required=False,
        help_text="Через запятую, например: hr, отпуска, регламенты",
    )

    def clean_tags(self) -> list[str]:
        return [name.strip() for name in self.cleaned_data["tags"].split(",") if name.strip()]


class DocumentImportUploadForm(forms.Form):
    document = forms.FileField(label="Документ (.txt, .docx, .pdf)")
