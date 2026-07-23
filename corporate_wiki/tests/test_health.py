import pytest


@pytest.mark.django_db
def test_liveness_ok(client):
    response = client.get("/health/live/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_ok(client):
    response = client.get("/health/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
