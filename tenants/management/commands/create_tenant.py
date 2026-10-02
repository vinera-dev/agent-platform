from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenants.models import ApiKey, Tenant


class Command(BaseCommand):
    help = "Create a tenant and issue its first API key. The key is shown only once."

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("--name", help="Display name (defaults to the slug)")
        parser.add_argument("--key-name", default="default", help="Label for the issued key")

    def handle(self, *args, slug, name, key_name, **options):
        tenant = Tenant(slug=slug, name=name or slug)
        try:
            tenant.full_clean()
        except ValidationError as error:
            raise CommandError("; ".join(error.messages)) from error
        with transaction.atomic():
            tenant.save()
            issued = ApiKey.issue(tenant, key_name)
        self.stdout.write(f"Tenant: {tenant.slug} ({tenant.id})")
        self.stdout.write(f"API key: {issued.raw_key}")
        self.stdout.write("Store this key now. It cannot be shown again.")
