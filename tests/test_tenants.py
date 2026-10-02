import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from tenants.models import Tenant

pytestmark = pytest.mark.django_db


def test_creates_a_tenant_with_defaults():
    tenant = Tenant.objects.create(name="Acme Vet", slug="acme-vet")

    assert tenant.is_active is True
    assert tenant.created_at is not None
    assert str(tenant.id).count("-") == 4
    assert str(tenant) == "acme-vet"


def test_slug_must_be_unique():
    Tenant.objects.create(name="Acme Vet", slug="acme-vet")

    with pytest.raises(IntegrityError), transaction.atomic():
        Tenant.objects.create(name="Other", slug="acme-vet")


def test_slug_rejects_invalid_characters():
    tenant = Tenant(name="Bad", slug="not a slug!")

    with pytest.raises(ValidationError):
        tenant.full_clean()


def test_tenants_are_ordered_by_name():
    Tenant.objects.create(name="Zeta", slug="zeta")
    Tenant.objects.create(name="Alpha", slug="alpha")

    assert [t.slug for t in Tenant.objects.all()] == ["alpha", "zeta"]
