from django.urls import path

from apps.articles import views

app_name = "taxonomy"

urlpatterns = [
    path("categories/", views.category_list, name="category_list"),
    path("categories/<str:slug>/", views.category_detail, name="category_detail"),
    path("tags/<str:slug>/", views.tag_detail, name="tag_detail"),
]
