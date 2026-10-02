import uuid

from django.db import models, transaction
from django.db.models import Max
from django.utils import timezone

from tenants.models import Tenant
from tenants.scoping import TenantQuerySet


class InvalidTransition(Exception):
    pass


class Agent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="agents")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="agent_unique_name_per_tenant"),
        ]

    def __str__(self) -> str:
        return self.name

    def new_version(self, **fields) -> "AgentVersion":
        latest = self.versions.aggregate(latest=Max("number"))["latest"] or 0
        return AgentVersion.objects.create(agent=self, number=latest + 1, **fields)


class AgentVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft"
        PUBLISHED = "published"
        ARCHIVED = "archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    system_prompt = models.TextField()
    model = models.CharField(max_length=80)
    parameters = models.JSONField(default=dict, blank=True)
    tools = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(fields=["agent", "number"], name="agentversion_unique_number"),
            models.UniqueConstraint(
                fields=["agent"],
                condition=models.Q(status="published"),
                name="agentversion_single_published",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.agent.name} v{self.number}"

    def publish(self) -> None:
        if self.status != self.Status.DRAFT:
            raise InvalidTransition(f"Only a draft can be published, not a {self.status} version.")
        with transaction.atomic():
            self.agent.versions.filter(status=self.Status.PUBLISHED).update(
                status=self.Status.ARCHIVED
            )
            self.status = self.Status.PUBLISHED
            self.published_at = timezone.now()
            self.save(update_fields=["status", "published_at"])

    def archive(self) -> None:
        if self.status == self.Status.ARCHIVED:
            raise InvalidTransition("The version is already archived.")
        self.status = self.Status.ARCHIVED
        self.save(update_fields=["status"])
