from django.urls import path

from apps.attachments import views

app_name = "attachments"

urlpatterns = [
    path("upload/", views.attachment_upload, name="upload"),
    path("<uuid:attachment_id>/download/", views.attachment_download, name="download"),
]
