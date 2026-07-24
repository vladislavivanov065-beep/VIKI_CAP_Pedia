from __future__ import annotations

from django import forms


def _split_names(raw: str) -> list[str]:
    return [name.strip() for name in raw.split(",") if name.strip()]


class ArticleCreateForm(forms.Form):
    title = forms.CharField(label="Заголовок", max_length=255)
    content_source = forms.CharField(
        label="Текст статьи (Markdown)", widget=forms.Textarea, required=False
    )
    edit_summary = forms.CharField(
        label="Краткое описание изменения", max_length=500, required=False
    )
    categories = forms.CharField(
        label="Категории",
        required=False,
        help_text="Через запятую, например: HR, Договоры. Новая категория создастся сама.",
    )
    tags = forms.CharField(
        label="Теги",
        required=False,
        help_text="Через запятую, например: hr, отпуска, регламенты",
    )

    def clean_categories(self) -> list[str]:
        return _split_names(self.cleaned_data["categories"])

    def clean_tags(self) -> list[str]:
        return _split_names(self.cleaned_data["tags"])


class ArticleEditForm(forms.Form):
    content_source = forms.CharField(
        label="Текст статьи (Markdown)", widget=forms.Textarea, required=False
    )
    edit_summary = forms.CharField(
        label="Краткое описание изменения", max_length=500, required=False
    )
    base_revision_id = forms.CharField(widget=forms.HiddenInput)
    article_version = forms.IntegerField(widget=forms.HiddenInput)
    categories = forms.CharField(
        label="Категории",
        required=False,
        help_text="Через запятую, например: HR, Договоры. Новая категория создастся сама.",
    )
    tags = forms.CharField(
        label="Теги",
        required=False,
        help_text="Через запятую, например: hr, отпуска, регламенты",
    )

    def clean_categories(self) -> list[str]:
        return _split_names(self.cleaned_data["categories"])

    def clean_tags(self) -> list[str]:
        return _split_names(self.cleaned_data["tags"])


class DocumentImportUploadForm(forms.Form):
    document = forms.FileField(label="Документ (.txt, .docx, .pdf)")
