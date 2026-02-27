from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth import get_user_model
from trackable.profiles.models import Profile
from trackable.timetracking.models import TimeEntry
from datetime import date, time
import os
import tempfile

User = get_user_model()


class BackupDBTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Software Developer",
            position="Senior Developer",
            weekly_hours=40,
            hourly_rate=75.50,
        )

    def test_backup_db_command(self):
        from django.conf import settings
        import shutil

        db_path = settings.DATABASES["default"]["NAME"]

        if os.path.exists(db_path):
            with tempfile.TemporaryDirectory() as tmpdir:
                backup_dir = os.path.join(tmpdir, "backups")
                os.makedirs(backup_dir, exist_ok=True)

                with self.settings(BACKUP_FILENAME="test_backup.sqlite3"):
                    call_command("backup_db")

                backup_path = os.path.join(backup_dir, "test_backup.sqlite3")
                self.assertTrue(os.path.exists(backup_path))


class SendMonthlyEmailsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.user.email_notifications_enabled = True
        self.user.save()

        self.profile = Profile.objects.create(
            user=self.user,
            title="Software Developer",
            position="Senior Developer",
            weekly_hours=40,
            hourly_rate=75.50,
        )

    def test_send_monthly_emails_command_last_day(self):
        from unittest.mock import patch
        from datetime import datetime

        today = date.today()

        if today.day != today.day:
            with patch(
                "trackable.core.management.commands.send_monthly_emails.datetime"
            ) as mock_datetime:
                mock_datetime.now.return_value = datetime(
                    today.year, today.month, 1, 23, 59
                )
                mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

                from django.core import mail

                with self.settings(
                    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
                ):
                    call_command("send_monthly_emails")

                    self.assertEqual(len(mail.outbox), 0)

    def test_send_monthly_emails_command_not_last_day(self):
        from unittest.mock import patch
        from datetime import datetime

        today = date.today()

        with patch(
            "trackable.core.management.commands.send_monthly_emails.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = datetime(
                today.year, today.month, 15, 12, 0
            )
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            from django.core import mail

            with self.settings(
                EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
            ):
                call_command("send_monthly_emails")

                self.assertEqual(len(mail.outbox), 0)
