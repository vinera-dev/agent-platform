import pytest
from rest_framework.test import APIClient

from tenants.models import ApiKey, Tenant


@pytest.fixture
def make_tenant(db):
    def factory(slug="acme-vet", name="Acme Vet", **extra):
        return Tenant.objects.create(slug=slug, name=name, **extra)

    return factory


@pytest.fixture
def tenant(make_tenant):
    return make_tenant()


@pytest.fixture
def issued_key(tenant):
    return ApiKey.issue(tenant, "backend")


@pytest.fixture
def client_for():
    def factory(raw_key):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key {raw_key}")
        return client

    return factory


@pytest.fixture(autouse=True)
def clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def eager():
    from config import celery_app

    previous = (celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield
    celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates = previous


@pytest.fixture(autouse=True)
def allowed_tool_domains(settings):
    settings.TOOL_ALLOWED_DOMAINS = ["example.com"]
