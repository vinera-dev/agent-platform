from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0003_run_ordering"),
        ("tenants", "0002_apikey"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="idempotency_key",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="run",
            name="request_fingerprint",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddConstraint(
            model_name="run",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key", ""), _negated=True),
                fields=("tenant", "idempotency_key"),
                name="run_unique_idempotency_key_per_tenant",
            ),
        ),
    ]
