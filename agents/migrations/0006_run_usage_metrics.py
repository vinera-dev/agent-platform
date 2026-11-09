from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0005_agentversion_knowledge_base"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="completion_tokens",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="run",
            name="estimated_cost_usd",
            field=models.DecimalField(decimal_places=6, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="run",
            name="latency_ms",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="run",
            name="prompt_tokens",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
