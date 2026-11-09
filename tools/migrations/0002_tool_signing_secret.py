import secrets

from django.db import migrations, models

import tools.models


def give_each_tool_its_own_secret(apps, schema_editor):
    Tool = apps.get_model("tools", "Tool")
    for tool in Tool.objects.all():
        tool.signing_secret = secrets.token_hex(32)
        tool.save(update_fields=["signing_secret"])


class Migration(migrations.Migration):
    dependencies = [
        ("tools", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tool",
            name="signing_secret",
            field=models.CharField(
                default=tools.models.generate_signing_secret, editable=False, max_length=64
            ),
        ),
        migrations.RunPython(give_each_tool_its_own_secret, migrations.RunPython.noop),
    ]
