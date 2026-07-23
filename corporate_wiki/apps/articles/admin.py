from django.contrib import admin

from apps.articles.models import Article, ArticleRedirect, ArticleRevision


class ArticleRevisionInline(admin.TabularInline):
    model = ArticleRevision
    extra = 0
    fields = ["revision_number", "title", "edited_by", "created_at", "edit_summary"]
    readonly_fields = ["revision_number", "title", "edited_by", "created_at", "edit_summary"]
    can_delete = False
    show_change_link = True
    ordering = ["-revision_number"]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "is_archived", "version", "created_by", "updated_at"]
    list_filter = ["is_archived"]
    search_fields = ["title", "slug"]
    readonly_fields = [
        "id",
        "title_normalized",
        "current_revision",
        "version",
        "created_by",
        "created_at",
        "updated_at",
        "archived_at",
        "archived_by",
    ]
    inlines = [ArticleRevisionInline]

    def has_delete_permission(self, request, obj=None):
        # Physical deletion of an article is never allowed through the UI
        # (section 4.1) — archiving is the only supported removal path.
        return False


@admin.register(ArticleRevision)
class ArticleRevisionAdmin(admin.ModelAdmin):
    list_display = ["article", "revision_number", "edited_by", "created_at"]
    search_fields = ["article__title", "edit_summary"]
    readonly_fields = [f.name for f in ArticleRevision._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ArticleRedirect)
class ArticleRedirectAdmin(admin.ModelAdmin):
    list_display = ["old_slug", "article", "created_by", "created_at"]
    search_fields = ["old_slug"]
    readonly_fields = [f.name for f in ArticleRedirect._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
