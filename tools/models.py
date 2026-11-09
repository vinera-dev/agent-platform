import uuid

from django.db import models

from tenants.models import Tenant
from tenants.scoping import TenantQuerySet


class Tool(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="tools")
    name = models.CharField(max_length=64)
    description = models.TextField(max_length=1000)
    input_schema = models.JSONField()
    endpoint_url = models.URLField(max_length=500)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="tool_unique_name_per_tenant"),
        ]

    def __str__(self) -> str:
        return self.name
