from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Holiday",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(unique=True)),
                ("name", models.CharField(max_length=200)),
            ],
            options={
                "verbose_name": "Holiday",
                "verbose_name_plural": "Holidays",
                "ordering": ["date"],
            },
        ),
    ]
