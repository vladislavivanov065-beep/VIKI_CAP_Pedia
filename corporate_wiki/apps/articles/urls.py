from django.urls import path

from apps.articles import views

app_name = "articles"

urlpatterns = [
    path("create/", views.article_create, name="create"),
    path("link-suggestions/", views.article_link_suggestions, name="link_suggestions"),
    path("sidebar-list/", views.article_sidebar_list, name="sidebar_list"),
    path("import/", views.document_import_upload, name="import_upload"),
    path("import/review/", views.document_import_review, name="import_review"),
    path(
        "import/review/<str:block_id>/",
        views.document_import_process_block,
        name="import_process_block",
    ),
    path("<str:slug>/", views.article_detail, name="detail"),
    path("<str:slug>/edit/", views.article_edit, name="edit"),
    path("<str:slug>/history/", views.article_history, name="history"),
    path("<str:slug>/compare/", views.article_compare, name="compare"),
    path(
        "<str:slug>/revisions/<int:revision_number>/",
        views.article_revision_detail,
        name="revision_detail",
    ),
    path(
        "<str:slug>/restore/<int:revision_number>/",
        views.article_restore,
        name="restore",
    ),
    path("<str:slug>/archive/", views.article_archive, name="archive"),
    path("<str:slug>/unarchive/", views.article_unarchive, name="unarchive"),
]
