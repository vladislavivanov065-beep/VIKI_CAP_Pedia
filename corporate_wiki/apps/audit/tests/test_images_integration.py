from io import BytesIO

import pytest

from apps.accounts.factories import UserFactory
from apps.audit.models import AuditLog
from apps.images import services
from apps.images.tests.factories import make_image_bytes

pytestmark = pytest.mark.django_db


def test_image_upload_is_audited():
    user = UserFactory()

    image = services.upload_article_image(
        file_obj=BytesIO(make_image_bytes()),
        original_filename="photo.png",
        uploaded_by=user,
        user_agent="ua-upload",
    )

    entry = AuditLog.objects.get(action="image.uploaded", object_id=image.pk)
    assert entry.actor == user
    assert entry.user_agent == "ua-upload"
    assert entry.metadata["original_filename"] == "photo.png"


def test_deduplicated_upload_is_not_audited_twice():
    user = UserFactory()
    data = make_image_bytes()

    services.upload_article_image(
        file_obj=BytesIO(data), original_filename="a.png", uploaded_by=user
    )
    services.upload_article_image(
        file_obj=BytesIO(data), original_filename="b.png", uploaded_by=user
    )

    assert AuditLog.objects.filter(action="image.uploaded").count() == 1
