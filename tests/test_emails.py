from django.test import TestCase
from django.core import mail
from django.contrib.auth import get_user_model
from django.test import override_settings
from trackable.core.management.commands.send_monthly_emails import Command

User = get_user_model()


class EmailTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_email_sent(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        from django.template.loader import render_to_string
        from django.conf import settings
        import html2text

        reset_url = f"http://testserver/accounts/reset/{uid}/{token}/"

        html_message = render_to_string(
            "emails/password_reset_email.html",
            {
                "user": self.user,
                "reset_url": reset_url,
            },
        )

        text_message = html2text.html2text(html_message)

        mail.send_mail(
            "Passwort zurücksetzen - Trackable",
            text_message,
            settings.DEFAULT_FROM_EMAIL,
            ["test@example.com"],
            html_message=html_message,
            fail_silently=False,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Passwort zurücksetzen", mail.outbox[0].subject)
        self.assertIn("test@example.com", mail.outbox[0].to)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_monthly_report_email_sent(self):
        from trackable.profiles.models import Profile
        from trackable.timetracking.models import TimeEntry
        from django.utils import timezone
        from datetime import date, time, timedelta

        self.user.email_notifications_enabled = True
        self.user.save()

        profile = Profile.objects.create(
            user=self.user,
            title="Test Job",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )

        today = date.today()
        TimeEntry.objects.create(
            profile=profile,
            date=today,
            start_time=time(9, 0),
            end_time=time(17, 0),
            pause_duration=1,
        )

        from django.template.loader import render_to_string
        from django.conf import settings
        import html2text
        from datetime import datetime
        import calendar

        month_name = datetime(today.year, today.month, 1).strftime("%B %Y")

        html_message = render_to_string(
            "emails/monthly_report_email.html",
            {
                "user": self.user,
                "profile": profile,
                "month_name": month_name,
                "total_hours": 7,
                "total_earnings": 350,
            },
        )

        text_message = html2text.html2text(html_message)

        mail.send_mail(
            f"Monatsbericht - {profile.title} - {month_name}",
            text_message,
            settings.DEFAULT_FROM_EMAIL,
            [self.user.email],
            html_message=html_message,
            fail_silently=False,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Monatsbericht", mail.outbox[0].subject)
