from django.urls import path

from apps.search import views

app_name = "search"

urlpatterns = [
    path("", views.search_results, name="search"),
    path("suggestions/", views.search_suggestions_view, name="suggestions"),
]
