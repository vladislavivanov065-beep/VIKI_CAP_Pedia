from django.contrib import admin

from apps.articles import services
from apps.articles.models import (
    Article,
    ArticleRedirect,
    ArticleRevision,
    ArticleSimilarity,
    Category,
    Tag,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "parent"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


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
    list_filter = ["is_archived", "categories", "tags"]
    search_fields = ["title", "slug"]
    filter_horizontal = ["categories", "tags"]
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
    actions = ["archive_selected", "restore_selected"]

    def has_delete_permission(self, request, obj=None):
        # Physical deletion of an article is never allowed through the UI
        # (section 4.1) — archiving is the only supported removal path.
        return False

    @admin.action(description="Архивировать выбранные статьи")
    def archive_selected(self, request, queryset):
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        count = 0
        for article in queryset.filter(is_archived=False):
            services.archive_article(
                article_id=article.pk, actor=request.user, user_agent=user_agent
            )
            count += 1
        self.message_user(request, f"Архивировано статей: {count}.")

    @admin.action(description="Восстановить выбранные статьи из архива")
    def restore_selected(self, request, queryset):
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        count = 0
        for article in queryset.filter(is_archived=True):
            services.restore_article(
                article_id=article.pk, actor=request.user, user_agent=user_agent
            )
            count += 1
        self.message_user(request, f"Восстановлено статей: {count}.")


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

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ArticleSimilarity)
class ArticleSimilarityAdmin(admin.ModelAdmin):
    list_display = ["article", "related_article", "score", "rank", "computed_at"]
    search_fields = ["article__title", "related_article__title"]
    readonly_fields = [f.name for f in ArticleSimilarity._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
