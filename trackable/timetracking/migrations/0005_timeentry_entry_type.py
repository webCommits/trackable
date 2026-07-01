# noqa: F401
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timetracking", "0004_activetimer"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeentry",
            name="entry_type",
            field=models.CharField(
                choices=[("actual", "Actual"), ("planned", "Planned")],
                default="actual",
                max_length=10,
            ),
        ),
    ]
