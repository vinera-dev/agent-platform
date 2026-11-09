import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("agents", "0006_run_usage_metrics"),
        ("tenants", "0002_apikey"),
    ]

    operations = [
        migrations.CreateModel(
            name="EvalDataset",
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
                (
                    "agent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="eval_datasets",
                        to="agents.agent",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="eval_datasets",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="EvalCase",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(blank=True, max_length=120)),
                ("input", models.JSONField()),
                ("expected_output", models.TextField(blank=True)),
                ("expected_contains", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="eval_cases",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "dataset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cases",
                        to="evaluation.evaldataset",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="evaldataset",
            constraint=models.UniqueConstraint(
                fields=("tenant", "name"), name="evaldataset_unique_name"
            ),
        ),
    ]
