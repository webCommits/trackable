from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timetracking", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeentry",
            name="notes",
            field=models.TextField(blank=True, null=True),
        ),
    ]
