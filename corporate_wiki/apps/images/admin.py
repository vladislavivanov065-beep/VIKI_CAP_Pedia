from django.contrib import admin
from django.utils.html import format_html

from apps.images.models import ArticleImage


@admin.register(ArticleImage)
class ArticleImageAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "original_filename",
        "mime_type",
        "file_size",
        "width",
        "height",
        "uploaded_by",
        "uploaded_at",
        "thumbnail_preview",
    ]
    search_fields = ["original_filename", "checksum"]
    readonly_fields = [
        "id",
        "thumbnail_preview",
        "mime_type",
        "file_size",
        "width",
        "height",
        "uploaded_by",
        "uploaded_at",
        "checksum",
    ]
    # Binary payloads never show up as plain editable text fields — only
    # the rendered thumbnail and metadata are visible (section 17).
    fields = [
        "id",
        "thumbnail_preview",
        "original_filename",
        "mime_type",
        "file_size",
        "width",
        "height",
        "alt_text",
        "caption",
        "uploaded_by",
        "uploaded_at",
        "checksum",
    ]

    def has_add_permission(self, request):
        return False

    @admin.display(description="Миниатюра")
    def thumbnail_preview(self, obj):
        if not obj.pk:
            return "—"
        return format_html(
            '<img src="/images/{}/thumbnail/" alt="" style="max-width: 160px;">', obj.pk
        )
