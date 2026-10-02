from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from tenants.models import ApiKey, Tenant

pytestmark = pytest.mark.django_db


def run(*args):
    out = StringIO()
    call_command("create_tenant", *args, stdout=out)
    return out.getvalue()


def extract_key(output):
    line = next(line for line in output.splitlines() if line.startswith("API key: "))
    return line.removeprefix("API key: ")


def test_creates_the_tenant_and_prints_a_working_key():
    output = run("acme-vet", "--name", "Acme Vet")
    raw_key = extract_key(output)

    tenant = Tenant.objects.get(slug="acme-vet")
    assert tenant.name == "Acme Vet"
    assert ApiKey.find_by_raw_key(raw_key).tenant == tenant


def test_the_key_is_not_recoverable_afterwards():
    raw_key = extract_key(run("acme-vet"))
    stored = ApiKey.objects.get()

    assert raw_key not in {stored.key_hash, stored.prefix, stored.name}
    assert not hasattr(stored, "raw_key")


def test_name_defaults_to_the_slug():
    run("acme-vet")

    assert Tenant.objects.get().name == "acme-vet"


def test_duplicate_slug_is_refused_without_creating_anything():
    run("acme-vet")

    with pytest.raises(CommandError):
        run("acme-vet")

    assert Tenant.objects.count() == 1
    assert ApiKey.objects.count() == 1


def test_invalid_slug_is_refused():
    with pytest.raises(CommandError):
        run("not a slug!")

    assert Tenant.objects.count() == 0
