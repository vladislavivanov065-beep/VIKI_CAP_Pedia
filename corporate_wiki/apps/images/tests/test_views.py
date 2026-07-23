import uuid
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.images import services
from apps.images.tests.factories import make_image_bytes

pytestmark = pytest.mark.django_db


def _uploaded_image(user):
    return services.upload_article_image(
        file_obj=BytesIO(make_image_bytes()),
        original_filename="a.png",
        uploaded_by=user,
    )


def test_anonymous_cannot_fetch_image(client):
    user = UserFactory()
    image = _uploaded_image(user)

    response = client.get(reverse("images:original", kwargs={"image_id": image.pk}))
    assert response.status_code == 302


def test_authenticated_user_can_fetch_image_with_correct_headers(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    image = _uploaded_image(user)

    response = client.get(reverse("images:original", kwargs={"image_id": image.pk}))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response["Content-Length"] == str(len(bytes(image.data)))
    assert response["ETag"]


def test_thumbnail_endpoint_serves_smaller_payload(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    image = _uploaded_image(user)

    response = client.get(reverse("images:thumbnail", kwargs={"image_id": image.pk}))
    assert response.status_code == 200
    assert len(response.content) == len(bytes(image.thumbnail_data))


def test_etag_enables_304_not_modified(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    image = _uploaded_image(user)

    first = client.get(reverse("images:original", kwargs={"image_id": image.pk}))
    etag = first["ETag"]

    second = client.get(
        reverse("images:original", kwargs={"image_id": image.pk}),
        HTTP_IF_NONE_MATCH=etag,
    )
    assert second.status_code == 304


def test_missing_image_returns_404(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("images:original", kwargs={"image_id": uuid.uuid4()}))
    assert response.status_code == 404


def test_upload_endpoint_creates_image_and_returns_markdown_snippet(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    upload = SimpleUploadedFile("test.png", make_image_bytes(), content_type="image/png")
    response = client.post(reverse("images:upload"), {"file": upload})

    assert response.status_code == 200
    data = response.json()
    assert data["markdown"].startswith("![[image:")
    assert data["id"]


def test_upload_endpoint_rejects_invalid_file(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    upload = SimpleUploadedFile("bad.png", b"not an image", content_type="image/png")
    response = client.post(reverse("images:upload"), {"file": upload})

    assert response.status_code == 400
    assert "error" in response.json()


def test_upload_endpoint_requires_post(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("images:upload"))
    assert response.status_code == 405


def test_upload_endpoint_requires_authentication(client):
    upload = SimpleUploadedFile("test.png", make_image_bytes(), content_type="image/png")
    response = client.post(reverse("images:upload"), {"file": upload})
    assert response.status_code == 302
