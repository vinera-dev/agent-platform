import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0004_run_idempotency"),
        ("knowledge", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentversion",
            name="knowledge_base",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="agent_versions",
                to="knowledge.knowledgebase",
            ),
        ),
    ]
