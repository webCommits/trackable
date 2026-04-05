from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("profiles", "0002_profile_internal_notes"),
        ("timetracking", "0003_vacationentry"),
    ]

    operations = [
        migrations.CreateModel(
            name="ActiveTimer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("start_time", models.DateTimeField()),
                ("pause_time", models.DateTimeField(blank=True, null=True)),
                ("total_paused_seconds", models.IntegerField(default=0)),
                ("is_paused", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="active_timers",
                        to="profiles.profile",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="active_timers",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("profile", "user")},
            },
        ),
    ]
