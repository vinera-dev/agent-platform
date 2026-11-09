import uuid

from django.db import models

from agents.models import Agent
from tenants.models import Tenant
from tenants.scoping import TenantQuerySet


class EvalDataset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="eval_datasets")
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="eval_datasets")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="evaldataset_unique_name"),
        ]

    def __str__(self) -> str:
        return self.name


class EvalCase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="eval_cases")
    dataset = models.ForeignKey(EvalDataset, on_delete=models.CASCADE, related_name="cases")
    name = models.CharField(max_length=120, blank=True)
    input = models.JSONField()
    expected_output = models.TextField(blank=True)
    expected_contains = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return self.name or str(self.id)
