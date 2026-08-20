from django.contrib import admin

from apps.comments.models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["article", "author", "parent", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["text", "author__username", "article__title"]
    autocomplete_fields = ["article", "parent", "author"]
