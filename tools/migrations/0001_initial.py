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
            name="Tool",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(max_length=64)),
                ("description", models.TextField(max_length=1000)),
                ("input_schema", models.JSONField()),
                ("endpoint_url", models.URLField(max_length=500)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tools",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant", "name"), name="tool_unique_name_per_tenant"
                    )
                ],
            },
        ),
    ]
