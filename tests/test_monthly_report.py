from datetime import date, time

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from trackable.core.reporting import (
    parse_monthly_report_day,
    report_period,
    report_period_label,
)
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.profiles.models import Profile
from trackable.timetracking.models import TimeEntry

User = get_user_model()


class ReportPeriodTest(TestCase):
    """Pure unit tests for trackable.core.reporting helpers."""

    def test_calendar_mode_on_last_day(self):
        period = report_period(date(2026, 11, 30), None)
        self.assertEqual(period, (date(2026, 11, 1), date(2026, 11, 30)))

    def test_calendar_mode_not_last_day(self):
        self.assertIsNone(report_period(date(2026, 11, 24), None))

    def test_calendar_mode_february(self):
        # Non-leap year: Feb has 28 days.
        period = report_period(date(2026, 2, 28), None)
        self.assertEqual(period, (date(2026, 2, 1), date(2026, 2, 28)))

    def test_cutoff_mode_not_send_day(self):
        self.assertIsNone(report_period(date(2026, 11, 23), 24))

    def test_cutoff_mode_basic(self):
        period = report_period(date(2026, 11, 24), 24)
        self.assertEqual(period, (date(2026, 10, 25), date(2026, 11, 24)))

    def test_cutoff_mode_year_boundary(self):
        period = report_period(date(2026, 1, 24), 24)
        self.assertEqual(period, (date(2025, 12, 25), date(2026, 1, 24)))

    def test_cutoff_mode_feb_to_march_28(self):
        # Feb has 28 days in 2026, so day 28 exists; start is the day after.
        period = report_period(date(2026, 3, 28), 28)
        self.assertEqual(period, (date(2026, 3, 1), date(2026, 3, 28)))

    def test_cutoff_mode_no_gaps_or_overlaps(self):
        first = report_period(date(2026, 3, 28), 28)
        second = report_period(date(2026, 4, 28), 28)
        self.assertEqual(first[1] + __import__("datetime").timedelta(days=1), second[0])

    def test_report_period_label_calendar_mode(self):
        label = report_period_label(date(2026, 11, 1), date(2026, 11, 30), None)
        self.assertEqual(label, "November 2026")

    def test_report_period_label_cutoff_mode(self):
        label = report_period_label(date(2026, 10, 25), date(2026, 11, 24), 24)
        self.assertEqual(label, "25.10.2026 – 24.11.2026")


class ParseMonthlyReportDayTest(TestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(parse_monthly_report_day(""))
        self.assertIsNone(parse_monthly_report_day(None))

    def test_valid_value(self):
        self.assertEqual(parse_monthly_report_day("24"), 24)
        self.assertEqual(parse_monthly_report_day(1), 1)
        self.assertEqual(parse_monthly_report_day(28), 28)

    def test_non_integer_raises(self):
        with self.assertRaises(ValueError):
            parse_monthly_report_day("not-a-number")

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            parse_monthly_report_day("0")
        with self.assertRaises(ValueError):
            parse_monthly_report_day("29")
        with self.assertRaises(ValueError):
            parse_monthly_report_day("-1")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SendMonthlyEmailsCommandTest(TestCase):
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

    def _add_entry(self, d, hours=8):
        TimeEntry.objects.create(
            profile=self.profile,
            date=d,
            start_time=time(9, 0),
            end_time=time(9 + hours, 0),
            pause_duration=0,
        )

    @override_settings(MONTHLY_REPORT_DAY_RAW="")
    def test_non_send_day_sends_nothing(self):
        self._add_entry(date(2026, 11, 15))
        call_command("send_monthly_emails", "--date", "2026-11-15")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(MONTHLY_REPORT_DAY_RAW="")
    def test_calendar_mode_sends_on_last_day(self):
        self._add_entry(date(2026, 11, 15))
        call_command("send_monthly_emails", "--date", "2026-11-30")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("November 2026", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ["employee@example.com"])

    @override_settings(MONTHLY_REPORT_DAY_RAW="24")
    def test_cutoff_mode_includes_boundary_entries_excludes_outside(self):
        # Period for today=2026-11-24, day=24 is 2026-10-25..2026-11-24.
        self._add_entry(date(2026, 10, 25))  # start boundary: included
        self._add_entry(date(2026, 11, 24))  # end boundary: included
        self._add_entry(date(2026, 10, 24))  # day before start: excluded
        self._add_entry(date(2026, 11, 25))  # day after end: excluded

        call_command("send_monthly_emails", "--date", "2026-11-24")

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("25.10.2026", email.subject)
        self.assertIn("24.11.2026", email.subject)
        # 2 included entries * 8h = 16h
        self.assertIn("16", email.body)

    @override_settings(MONTHLY_REPORT_DAY_RAW="not-a-number")
    def test_invalid_monthly_report_day_raises_command_error(self):
        self._add_entry(date(2026, 11, 15))
        with self.assertRaises(CommandError):
            call_command("send_monthly_emails", "--date", "2026-11-30")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(MONTHLY_REPORT_DAY_RAW="")
    def test_dry_run_sends_nothing(self):
        self._add_entry(date(2026, 11, 15))
        call_command("send_monthly_emails", "--date", "2026-11-30", "--dry-run")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(MONTHLY_REPORT_DAY_RAW="")
    def test_skips_profiles_without_entries_in_period(self):
        # Entry exists but outside the period for this send day.
        self._add_entry(date(2026, 10, 15))
        call_command("send_monthly_emails", "--date", "2026-11-30")
        self.assertEqual(len(mail.outbox), 0)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MONTHLY_REPORT_DAY_RAW="",
)
class RecipientMatrixTest(TestCase):
    """Covers the to/bcc recipient matrix: notifications on/off x org email
    set/unset/same-as-user."""

    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager",
            email="manager@example.com",
            password="testpass123",
        )
        self.org = Organization.objects.create(name="Acme Corp", created_by=self.manager)
        OrganizationMembership.objects.create(
            organization=self.org, user=self.manager, role="manager"
        )

    def _make_employee(self, username, email, notifications_enabled, is_active=True):
        user = User.objects.create_user(
            username=username,
            email=email,
            password="testpass123",
            email_notifications_enabled=notifications_enabled,
            is_active=is_active,
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=user, role="employee"
        )
        profile = Profile.objects.create(
            user=user,
            title="Developer",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        TimeEntry.objects.create(
            profile=profile,
            date=date(2026, 11, 15),
            start_time=time(9, 0),
            end_time=time(17, 0),
            pause_duration=0,
        )
        return user, profile

    def _send(self):
        mail.outbox.clear()
        call_command("send_monthly_emails", "--date", "2026-11-30")

    def test_notifications_on_no_org_email(self):
        self._make_employee("alice", "alice@example.com", True)
        self._send()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alice@example.com"])
        self.assertEqual(mail.outbox[0].bcc, [])

    def test_notifications_on_org_email_set_different(self):
        self.org.monthly_report_email = "reports@acme.example"
        self.org.save()
        self._make_employee("bob", "bob@example.com", True)
        self._send()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["bob@example.com"])
        self.assertEqual(mail.outbox[0].bcc, ["reports@acme.example"])

    def test_notifications_on_org_email_same_as_user_case_insensitive(self):
        self.org.monthly_report_email = "CAROL@example.com"
        self.org.save()
        self._make_employee("carol", "carol@example.com", True)
        self._send()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["carol@example.com"])
        self.assertEqual(mail.outbox[0].bcc, [])

    def test_notifications_off_org_email_unset_skips(self):
        self._make_employee("dave", "dave@example.com", False)
        self._send()
        self.assertEqual(len(mail.outbox), 0)

    def test_notifications_off_org_email_set_sends_to_org_only(self):
        self.org.monthly_report_email = "reports@acme.example"
        self.org.save()
        self._make_employee("erin", "erin@example.com", False)
        self._send()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reports@acme.example"])
        self.assertEqual(mail.outbox[0].bcc, [])


class ProfileMonthlyMethodsUnchangedTest(TestCase):
    """get_monthly_entries/hours/earnings must keep their pre-existing
    results after being refactored to delegate to get_entries_between."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Developer",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 11, 1),
            start_time=time(9, 0),
            end_time=time(17, 0),
            pause_duration=0,
        )
        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 11, 30),
            start_time=time(9, 0),
            end_time=time(13, 0),
            pause_duration=0,
        )
        # Outside the month: must not be counted.
        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 12, 1),
            start_time=time(9, 0),
            end_time=time(17, 0),
            pause_duration=0,
        )

    def test_get_monthly_hours(self):
        self.assertEqual(self.profile.get_monthly_hours(2026, 11), 12)

    def test_get_monthly_earnings(self):
        self.assertEqual(self.profile.get_monthly_earnings(2026, 11), 600)

    def test_get_monthly_entries_count(self):
        self.assertEqual(self.profile.get_monthly_entries(2026, 11).count(), 2)

    def test_get_entries_between_matches_get_monthly_entries(self):
        monthly = set(self.profile.get_monthly_entries(2026, 11).values_list("id", flat=True))
        between = set(
            self.profile.get_entries_between(
                date(2026, 11, 1), date(2026, 11, 30)
            ).values_list("id", flat=True)
        )
        self.assertEqual(monthly, between)
