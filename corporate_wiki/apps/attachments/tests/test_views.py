from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.attachments import services
from apps.attachments.tests.factories import make_txt_bytes

pytestmark = pytest.mark.django_db


def _uploaded(user):
    return services.upload_attachment(
        file_obj=BytesIO(make_txt_bytes("Содержимое файла.")),
        original_filename="документ.txt",
        uploaded_by=user,
    )


def test_anonymous_cannot_download_attachment(client):
    user = UserFactory()
    attachment = _uploaded(user)

    response = client.get(reverse("attachments:download", kwargs={"attachment_id": attachment.pk}))
    assert response.status_code == 302


def test_authenticated_user_can_download_attachment(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    attachment = _uploaded(user)

    response = client.get(reverse("attachments:download", kwargs={"attachment_id": attachment.pk}))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain"
    assert "attachment" in response["Content-Disposition"]
    assert response.content == "Содержимое файла.".encode("utf-8")


def test_upload_endpoint_returns_markdown_embed(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    upload = SimpleUploadedFile("notes.txt", make_txt_bytes("Пример."), content_type="text/plain")
    response = client.post(reverse("attachments:upload"), {"file": upload})

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "notes.txt"
    assert data["markdown"] == f"[[attachment:{data['id']}]]"


def test_upload_endpoint_rejects_unsupported_format(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    upload = SimpleUploadedFile(
        "virus.exe", b"not a document", content_type="application/octet-stream"
    )
    response = client.post(reverse("attachments:upload"), {"file": upload})

    assert response.status_code == 400
    assert "error" in response.json()


def test_upload_endpoint_requires_post(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("attachments:upload"))
    assert response.status_code == 405
