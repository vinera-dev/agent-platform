from rest_framework.test import APIClient


def test_health_reports_ok():
    response = APIClient().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_rejects_unsafe_methods():
    response = APIClient().post("/health")

    assert response.status_code == 405
