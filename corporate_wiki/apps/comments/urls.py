from django.urls import path

from apps.comments import views

app_name = "comments"

urlpatterns = [
    path("<str:slug>/", views.comment_create, name="create"),
]
