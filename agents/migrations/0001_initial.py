import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("tenants", "0002_apikey"),
    ]

    operations = [
        migrations.CreateModel(
            name="Agent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True, max_length=1000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agents",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="AgentVersion",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("number", models.PositiveIntegerField()),
                ("system_prompt", models.TextField()),
                ("model", models.CharField(max_length=80)),
                ("parameters", models.JSONField(blank=True, default=dict)),
                ("tools", models.JSONField(blank=True, default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("published", "Published"),
                            ("archived", "Archived"),
                        ],
                        default="draft",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                (
                    "agent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="agents.agent",
                    ),
                ),
            ],
            options={
                "ordering": ["-number"],
            },
        ),
        migrations.AddConstraint(
            model_name="agent",
            constraint=models.UniqueConstraint(
                fields=("tenant", "name"), name="agent_unique_name_per_tenant"
            ),
        ),
        migrations.AddConstraint(
            model_name="agentversion",
            constraint=models.UniqueConstraint(
                fields=("agent", "number"), name="agentversion_unique_number"
            ),
        ),
        migrations.AddConstraint(
            model_name="agentversion",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "published")),
                fields=("agent",),
                name="agentversion_single_published",
            ),
        ),
    ]
