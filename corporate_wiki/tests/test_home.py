import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_home_page_renders_base_layout_for_authenticated_user(client):
    user = UserFactory(must_change_password=False, first_name="Анна", last_name="Иванова")
    client.force_login(user)

    response = client.get(reverse("home"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Анна Иванова" in content
    assert 'class="topbar"' in content
    assert 'class="sidebar"' in content


def test_home_page_shows_admin_link_only_for_staff(client):
    staff = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(staff)
    response = client.get(reverse("home"))
    assert reverse("admin:index") in response.content.decode()

    client.logout()

    regular = UserFactory(must_change_password=False, is_staff=False)
    client.force_login(regular)
    response = client.get(reverse("home"))
    assert reverse("admin:index") not in response.content.decode()
