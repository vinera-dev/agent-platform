import uuid

import django.db.models.deletion
import pgvector.django.indexes
import pgvector.django.vector
from django.db import migrations, models
from pgvector.django import VectorExtension


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("tenants", "0002_apikey"),
    ]

    operations = [
        VectorExtension(),
        migrations.CreateModel(
            name="KnowledgeBase",
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
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="knowledge_bases",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("content", models.TextField()),
                ("size_bytes", models.PositiveIntegerField()),
                ("content_sha256", models.CharField(max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("ready", "Ready"), ("failed", "Failed")],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("ingested_at", models.DateTimeField(blank=True, null=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "knowledge_base",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="knowledge.knowledgebase",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="Chunk",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("position", models.PositiveIntegerField()),
                ("text", models.TextField()),
                ("embedding", pgvector.django.vector.VectorField(dimensions=256)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="knowledge.document",
                    ),
                ),
            ],
            options={
                "ordering": ["document_id", "position"],
                "indexes": [
                    models.Index(fields=["tenant"], name="knowledge_c_tenant__273837_idx"),
                    pgvector.django.indexes.HnswIndex(
                        ef_construction=64,
                        fields=["embedding"],
                        m=16,
                        name="chunk_embedding_hnsw",
                        opclasses=["vector_cosine_ops"],
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("document", "position"), name="chunk_unique_position"
                    )
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="knowledgebase",
            constraint=models.UniqueConstraint(
                fields=("tenant", "name"), name="knowledgebase_unique_name_per_tenant"
            ),
        ),
    ]
