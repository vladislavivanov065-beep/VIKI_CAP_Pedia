from django.urls import path

from apps.articles import views

app_name = "articles"

urlpatterns = [
    path("create/", views.article_create, name="create"),
    path("preview/", views.article_preview, name="preview"),
    path("<str:slug>/", views.article_detail, name="detail"),
    path("<str:slug>/edit/", views.article_edit, name="edit"),
]
