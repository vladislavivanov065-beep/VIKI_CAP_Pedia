from django.urls import path

from apps.images import views

app_name = "images"

urlpatterns = [
    path("upload/", views.image_upload, name="upload"),
    path("<uuid:image_id>/", views.image_original, name="original"),
    path("<uuid:image_id>/thumbnail/", views.image_thumbnail, name="thumbnail"),
]
