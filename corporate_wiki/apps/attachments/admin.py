from django.contrib import admin

from apps.attachments.models import ArticleAttachment


@admin.register(ArticleAttachment)
class ArticleAttachmentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "original_filename",
        "mime_type",
        "file_size",
        "uploaded_by",
        "uploaded_at",
    ]
    search_fields = ["original_filename", "checksum"]
    readonly_fields = [
        "id",
        "original_filename",
        "mime_type",
        "file_size",
        "uploaded_by",
        "uploaded_at",
        "checksum",
    ]
    fields = [
        "id",
        "original_filename",
        "mime_type",
        "file_size",
        "uploaded_by",
        "uploaded_at",
        "checksum",
    ]

    def has_add_permission(self, request):
        return False
