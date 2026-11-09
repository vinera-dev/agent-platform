from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0002_run"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="run",
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]
