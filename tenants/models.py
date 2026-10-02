import hashlib
import hmac
import secrets
import uuid
from typing import NamedTuple, Self

from django.db import models
from django.utils import timezone

API_KEY_PREFIX_BYTES = 4
API_KEY_SECRET_BYTES = 32
API_KEY_SEPARATOR = "."
API_KEY_PREFIX_LENGTH = API_KEY_PREFIX_BYTES * 2


def hash_api_key_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=63, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.slug


class IssuedApiKey(NamedTuple):
    api_key: "ApiKey"
    raw_key: str


class ApiKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=120)
    prefix = models.CharField(max_length=API_KEY_PREFIX_LENGTH, unique=True, editable=False)
    key_hash = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.prefix}…"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @classmethod
    def issue(cls, tenant: Tenant, name: str) -> IssuedApiKey:
        prefix = secrets.token_hex(API_KEY_PREFIX_BYTES)
        secret = secrets.token_urlsafe(API_KEY_SECRET_BYTES)
        api_key = cls.objects.create(
            tenant=tenant,
            name=name,
            prefix=prefix,
            key_hash=hash_api_key_secret(secret),
        )
        return IssuedApiKey(api_key, f"{prefix}{API_KEY_SEPARATOR}{secret}")

    @classmethod
    def find_by_raw_key(cls, raw_key: str) -> Self | None:
        prefix, separator, secret = raw_key.partition(API_KEY_SEPARATOR)
        if not separator or len(prefix) != API_KEY_PREFIX_LENGTH or not secret:
            return None
        api_key = cls.objects.select_related("tenant").filter(prefix=prefix).first()
        if api_key is None:
            return None
        if not hmac.compare_digest(api_key.key_hash, hash_api_key_secret(secret)):
            return None
        return api_key

    def revoke(self) -> None:
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at"])
