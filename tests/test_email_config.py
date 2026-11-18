"""Tests for SiteConfiguration-based email overrides (host/connection and
from-address), and that all call sites actually use them."""
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from trackable.core.email import get_effective_connection, get_effective_from_email
from trackable.core.models import SiteConfiguration
from trackable.profiles.models import Profile
from trackable.timetracking.models import TimeEntry

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class GetEffectiveFromEmailTest(TestCase):
    def test_falls_back_to_settings_when_db_empty(self):
        config = SiteConfiguration.get()
        config.default_from_email = ""
        config.save()
        self.assertEqual(get_effective_from_email(), settings.DEFAULT_FROM_EMAIL)

    def test_uses_db_value_when_set(self):
        config = SiteConfiguration.get()
        config.default_from_email = "custom@example.com"
        config.save()
        self.assertEqual(get_effective_from_email(), "custom@example.com")

    def test_strips_whitespace_from_db_value(self):
        config = SiteConfiguration.get()
        config.default_from_email = "  custom@example.com  "
        config.save()
        self.assertEqual(get_effective_from_email(), "custom@example.com")

    def test_whitespace_only_db_value_falls_back_to_settings(self):
        config = SiteConfiguration.get()
        config.default_from_email = "   "
        config.save()
        self.assertEqual(get_effective_from_email(), settings.DEFAULT_FROM_EMAIL)


class GetEffectiveConnectionUnchangedTest(TestCase):
    def test_returns_none_when_db_host_empty(self):
        config = SiteConfiguration.get()
        config.email_host = ""
        config.save()
        self.assertIsNone(get_effective_connection())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    def test_returns_connection_when_db_host_set(self):
        config = SiteConfiguration.get()
        config.email_host = "smtp.example.com"
        config.email_port = 2525
        config.email_use_tls = False
        config.email_host_user = "user@example.com"
        config.email_host_password = "secret"
        config.save()
        connection = get_effective_connection()
        self.assertIsNotNone(connection)
        self.assertEqual(connection.host, "smtp.example.com")
        self.assertEqual(connection.port, 2525)
        self.assertFalse(connection.use_tls)
        self.assertEqual(connection.username, "user@example.com")
        self.assertEqual(connection.password, "secret")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CallSitesUseEffectiveFromEmailTest(TestCase):
    """Each call site must use get_effective_from_email() for the From
    address instead of settings.DEFAULT_FROM_EMAIL directly."""

    def setUp(self):
        self.client = Client()
        config = SiteConfiguration.get()
        config.default_from_email = "configured@example.com"
        config.save()

    def test_password_reset_uses_db_from_email(self):
        User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.client.post(
            "/accounts/password-reset/", {"email": "test@example.com"}
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "configured@example.com")

    def test_email_confirmation_uses_db_from_email(self):
        self.client.post(
            "/accounts/register/",
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "first_name": "New",
                "last_name": "User",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "configured@example.com")

    def test_admin_email_test_uses_db_from_email(self):
        User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )
        self.client.login(username="admin", password="adminpass123")
        self.client.post("/admin/email-test/", {"recipient": "to@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "configured@example.com")

    def test_admin_email_test_page_displays_db_from_email(self):
        User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get("/admin/email-test/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "configured@example.com")

    def test_password_reset_falls_back_to_settings_when_db_empty(self):
        config = SiteConfiguration.get()
        config.default_from_email = ""
        config.save()
        User.objects.create_user(
            username="testuser2", email="test2@example.com", password="testpass123"
        )
        self.client.post(
            "/accounts/password-reset/", {"email": "test2@example.com"}
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, settings.DEFAULT_FROM_EMAIL)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MONTHLY_REPORT_DAY_RAW="",
)
class MonthlyReportUsesEffectiveEmailSettingsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="employee",
            email="employee@example.com",
            password="testpass123",
            email_notifications_enabled=True,
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Developer",
            position="Senior Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        from datetime import date, time

        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 11, 15),
            start_time=time(9, 0),
            end_time=time(17, 0),
            pause_duration=0,
        )

    def test_uses_db_from_email(self):
        config = SiteConfiguration.get()
        config.default_from_email = "reports@example.com"
        config.save()
        call_command("send_monthly_emails", "--date", "2026-11-30")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "reports@example.com")

    def test_falls_back_to_settings_from_email_when_db_empty(self):
        config = SiteConfiguration.get()
        config.default_from_email = ""
        config.save()
        call_command("send_monthly_emails", "--date", "2026-11-30")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, settings.DEFAULT_FROM_EMAIL)

    @patch("trackable.core.management.commands.send_monthly_emails.get_effective_connection")
    def test_passes_effective_connection_to_messages(self, mock_get_connection):
        from django.core.mail import get_connection

        locmem_connection = get_connection(
            backend="django.core.mail.backends.locmem.EmailBackend"
        )
        mock_get_connection.return_value = locmem_connection

        call_command("send_monthly_emails", "--date", "2026-11-30")

        mock_get_connection.assert_called_once()
        self.assertEqual(len(mail.outbox), 1)

    def test_dry_run_does_not_fetch_connection(self):
        with patch(
            "trackable.core.management.commands.send_monthly_emails.get_effective_connection"
        ) as mock_get_connection:
            call_command("send_monthly_emails", "--date", "2026-11-30", "--dry-run")
            mock_get_connection.assert_not_called()
