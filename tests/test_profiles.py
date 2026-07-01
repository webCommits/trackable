from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from datetime import date, time
from trackable.profiles.models import Profile
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.core.models import Holiday
from trackable.timetracking.models import (
    ENTRY_TYPE_ACTUAL,
    ENTRY_TYPE_PLANNED,
    TimeEntry,
)

User = get_user_model()


class ProfileModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_create_profile(self):
        profile = Profile.objects.create(
            user=self.user,
            title="Software Developer",
            position="Senior Developer",
            address="Berlin, Germany",
            weekly_hours=40,
            hourly_rate=75.50,
        )

        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.title, "Software Developer")
        self.assertEqual(profile.weekly_hours, 40)
        self.assertEqual(profile.hourly_rate, 75.50)

    def test_profile_str(self):
        profile = Profile.objects.create(
            user=self.user,
            title="Software Developer",
            position="Senior Developer",
            weekly_hours=40,
            hourly_rate=75.50,
        )

        self.assertEqual(str(profile), "Software Developer - Senior Developer")


class ProfileViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")

    def test_profile_create(self):
        response = self.client.post(
            reverse("profile_create"),
            {
                "title": "Software Developer",
                "position": "Senior Developer",
                "address": "Berlin, Germany",
                "weekly_hours_hours": 40,
                "weekly_hours_minutes": 0,
                "hourly_rate": 75.50,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Profile.objects.filter(user=self.user).exists())

    def test_profile_list(self):
        Profile.objects.create(
            user=self.user,
            title="Job 1",
            position="Position 1",
            weekly_hours=40,
            hourly_rate=50,
        )

        response = self.client.get(reverse("profile_list"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Job 1")

    def test_profile_detail(self):
        profile = Profile.objects.create(
            user=self.user,
            title="Software Developer",
            position="Senior Developer",
            weekly_hours=40,
            hourly_rate=75.50,
        )

        response = self.client.get(reverse("profile_detail", kwargs={"pk": profile.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Software Developer")


class TimeAccountTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="test123", email="test@example.com"
        )
        self.org = Organization.objects.create(
            name="Test AG", slug="test-ag", created_by=self.user
        )
        self.membership = OrganizationMembership.objects.create(
            user=self.user, organization=self.org, role="manager"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Engineer",
            position="Dev",
            weekly_hours=40,
            hourly_rate=50,
        )

    def test_get_target_hours_full_month(self):
        """40h/Woche × 4,348 = 173,92h (kein Pro-rata)"""
        target = self.profile.get_target_hours(2026, 5)
        self.assertEqual(target, 173.92)

    def test_get_target_hours_february_2026(self):
        """Februar hat weniger Tage, aber Faktor bleibt 4,348 → 173,92h"""
        target = self.profile.get_target_hours(2026, 2)
        self.assertEqual(target, 173.92)

    def test_target_hours_ignores_holidays(self):
        """Feiertage kürzen die Soll-Stunden nicht mehr."""
        Holiday.objects.create(
            date=date(2026, 5, 1), name="Tag der Arbeit", organization=self.org
        )
        target = self.profile.get_target_hours(2026, 5)
        self.assertEqual(target, 173.92)

    def test_get_balance_negative(self):
        """No entries → balance = -173.92"""
        balance = self.profile.get_balance(2026, 5)
        self.assertEqual(balance, -173.92)

    def test_working_days_excludes_weekends(self):
        days = self.profile._get_working_days_in_month(2026, 2)
        self.assertEqual(days, 20)

    def test_working_days_with_org_holiday(self):
        Holiday.objects.create(
            date=date(2026, 5, 1), name="Tag der Arbeit", organization=self.org
        )
        days = self.profile._get_working_days_in_month(2026, 5)
        self.assertEqual(days, 20)

    def test_profile_detail_shows_time_account(self):
        self.client.login(username="testuser", password="test123")
        response = self.client.get(
            reverse("profile_detail", kwargs={"pk": self.profile.pk})
        )
        self.assertEqual(response.status_code, 200)
        # English locale in tests, check for English terms
        self.assertContains(response, "Target")
        self.assertContains(response, "Balance")

    def test_target_hours_uses_weekly_target_hours_when_set(self):
        """Overridden target → 30 × 4,348 = 130,44h"""
        self.profile.weekly_target_hours = 30
        self.profile.save()
        target = self.profile.get_target_hours(2026, 5)
        self.assertEqual(target, 30 * 4.348)

    def test_target_hours_falls_back_to_weekly_hours(self):
        """weekly_target_hours=None → 40 × 4,348 = 173,92h"""
        self.profile.weekly_target_hours = None
        self.profile.save()
        target = self.profile.get_target_hours(2026, 5)
        self.assertEqual(target, 173.92)

    def test_target_hours_cleared_to_none(self):
        """Setting None falls back to weekly_hours"""
        self.profile.weekly_target_hours = 30
        self.profile.save()
        self.profile.weekly_target_hours = None
        self.profile.save()
        target = self.profile.get_target_hours(2026, 5)
        self.assertEqual(target, 173.92)

    def test_target_hours_with_contract_start_later(self):
        """Contract starts June 10 → Pro-rata 15/22 der vollen Soll-Stunden."""
        self.profile.contract_start_date = date(2026, 6, 10)
        self.profile.save()
        target = self.profile.get_target_hours(2026, 6)
        # June 2026: 22 weekdays total, 15 weekdays from June 10
        expected = round(40 * 4.348 * 15 / 22, 2)
        self.assertEqual(target, expected)

    def test_target_hours_with_contract_end_before_month(self):
        """Contract ends June 15 → Pro-rata 11/22 der vollen Soll-Stunden."""
        self.profile.contract_end_date = date(2026, 6, 15)
        self.profile.save()
        target = self.profile.get_target_hours(2026, 6)
        # June 2026: 22 weekdays total, 11 weekdays until June 15
        expected = round(40 * 4.348 * 11 / 22, 2)
        self.assertEqual(target, expected)

    def test_target_hours_with_contract_in_middle(self):
        """Contract June 10 to June 20 → Pro-rata 8/22 der vollen Soll-Stunden."""
        self.profile.contract_start_date = date(2026, 6, 10)
        self.profile.contract_end_date = date(2026, 6, 20)
        self.profile.save()
        target = self.profile.get_target_hours(2026, 6)
        # June 2026: 22 weekdays total, 8 weekdays June 10-20
        expected = round(40 * 4.348 * 8 / 22, 2)
        self.assertEqual(target, expected)

    def test_target_hours_before_contract_start(self):
        """Vertrag beginnt erst im Juli → Juni = 0 Soll-Stunden."""
        self.profile.contract_start_date = date(2026, 7, 1)
        self.profile.save()
        target = self.profile.get_target_hours(2026, 6)
        self.assertEqual(target, 0.0)

    def test_target_hours_after_contract_end(self):
        """Vertrag endete im Mai → Juni = 0 Soll-Stunden."""
        self.profile.contract_end_date = date(2026, 5, 31)
        self.profile.save()
        target = self.profile.get_target_hours(2026, 6)
        self.assertEqual(target, 0.0)

    def test_target_hours_ignores_contract_dates_when_null(self):
        """Null contract dates → voller Monat = 173,92h."""
        self.profile.contract_start_date = None
        self.profile.contract_end_date = None
        self.profile.save()
        target = self.profile.get_target_hours(2026, 5)
        self.assertEqual(target, 173.92)

    def test_planned_entry_does_not_affect_monthly_hours(self):
        """Planned entries created via weekly calendar should not affect monthly hours."""
        from datetime import datetime
        entry = TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 5, 15),
            start_time=datetime.strptime("09:00", "%H:%M").time(),
            end_time=datetime.strptime("17:00", "%H:%M").time(),
            entry_type=ENTRY_TYPE_PLANNED,
        )
        hours = self.profile.get_monthly_hours(2026, 5)
        self.assertEqual(hours, 0)

    def test_actual_entry_affects_monthly_hours(self):
        """Actual entries should count toward monthly hours."""
        from datetime import datetime
        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 5, 15),
            start_time=datetime.strptime("09:00", "%H:%M").time(),
            end_time=datetime.strptime("17:00", "%H:%M").time(),
            entry_type=ENTRY_TYPE_ACTUAL,
        )
        hours = self.profile.get_monthly_hours(2026, 5)
        self.assertEqual(hours, 8.0)

    def test_planned_entry_does_not_affect_monthly_earnings(self):
        """Planned entries should not affect monthly earnings."""
        from datetime import datetime
        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 5, 15),
            start_time=datetime.strptime("09:00", "%H:%M").time(),
            end_time=datetime.strptime("17:00", "%H:%M").time(),
            entry_type=ENTRY_TYPE_PLANNED,
        )
        earnings = self.profile.get_monthly_earnings(2026, 5)
        self.assertEqual(earnings, 0)

    def test_planned_entry_does_not_affect_balance(self):
        """Planned entries should not affect balance calculation."""
        from datetime import datetime
        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 5, 15),
            start_time=datetime.strptime("09:00", "%H:%M").time(),
            end_time=datetime.strptime("17:00", "%H:%M").time(),
            entry_type=ENTRY_TYPE_PLANNED,
        )
        balance = self.profile.get_balance(2026, 5)
        self.assertEqual(balance, -173.92)

    def test_get_monthly_entries_excludes_planned(self):
        """get_monthly_entries should only return actual entries."""
        from datetime import datetime
        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 5, 10),
            start_time=datetime.strptime("09:00", "%H:%M").time(),
            end_time=datetime.strptime("17:00", "%H:%M").time(),
            entry_type=ENTRY_TYPE_ACTUAL,
        )
        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 5, 15),
            start_time=datetime.strptime("09:00", "%H:%M").time(),
            end_time=datetime.strptime("17:00", "%H:%M").time(),
            entry_type=ENTRY_TYPE_PLANNED,
        )
        entries = self.profile.get_monthly_entries(2026, 5)
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().entry_type, ENTRY_TYPE_ACTUAL)

    def test_default_entry_type_is_actual(self):
        """New TimeEntry without explicit entry_type should default to actual."""
        from datetime import datetime
        entry = TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 5, 20),
            start_time=datetime.strptime("09:00", "%H:%M").time(),
            end_time=datetime.strptime("17:00", "%H:%M").time(),
        )
        self.assertEqual(entry.entry_type, ENTRY_TYPE_ACTUAL)
        hours = self.profile.get_monthly_hours(2026, 5)
        self.assertEqual(hours, 8.0)


class MonthlyAccountRowsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="test123", email="test@example.com"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Engineer",
            position="Dev",
            weekly_hours=40,
            hourly_rate=50,
        )

    def _make_entry(self, year, month, day, start_h, end_h, entry_type=ENTRY_TYPE_ACTUAL):
        return TimeEntry.objects.create(
            profile=self.profile,
            date=date(year, month, day),
            start_time=time(start_h, 0),
            end_time=time(end_h, 0),
            entry_type=entry_type,
        )

    def test_empty_no_contract_no_entries_starts_at_until_month(self):
        rows = self.profile.get_monthly_account_rows(until_year=2026, until_month=6)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["year"], 2026)
        self.assertEqual(rows[0]["month"], 6)

    def test_planned_only_no_contract_start_does_not_extend_range(self):
        self._make_entry(2026, 5, 15, 9, 17, entry_type=ENTRY_TYPE_PLANNED)
        self._make_entry(2026, 6, 10, 9, 17, entry_type=ENTRY_TYPE_PLANNED)
        rows = self.profile.get_monthly_account_rows(until_year=2026, until_month=7)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["year"], 2026)
        self.assertEqual(rows[0]["month"], 7)
        self.assertEqual(rows[0]["hours"], 0.0)

    def test_balance_is_monthly_not_cumulative(self):
        self.profile.contract_start_date = date(2026, 5, 1)
        self.profile.save()
        self._make_entry(2026, 5, 10, 9, 17)
        self._make_entry(2026, 5, 15, 9, 17)
        self._make_entry(2026, 6, 5, 9, 17)

        rows = self.profile.get_monthly_account_rows(until_year=2026, until_month=6)
        self.assertEqual(len(rows), 2)

        june = rows[0]
        may = rows[1]
        self.assertEqual(may["month"], 5)
        self.assertEqual(may["hours"], 16.0)
        self.assertEqual(may["target_hours"], 173.92)
        self.assertEqual(may["balance"], round(16.0 - 173.92, 2))
        self.assertEqual(may["cumulative_balance"], round(16.0 - 173.92, 2))

        self.assertEqual(june["month"], 6)
        self.assertEqual(june["hours"], 8.0)
        self.assertEqual(june["target_hours"], 173.92)
        self.assertEqual(june["balance"], round(8.0 - 173.92, 2))
        may_balance = round(16.0 - 173.92, 2)
        june_balance = round(8.0 - 173.92, 2)
        self.assertEqual(june["cumulative_balance"], round(may_balance + june_balance, 2))
        self.assertNotEqual(june["balance"], june["cumulative_balance"])

    def test_cumulative_carries_deficit_forward(self):
        self.profile.contract_start_date = date(2026, 5, 1)
        self.profile.save()
        self._make_entry(2026, 5, 10, 9, 17)

        rows = self.profile.get_monthly_account_rows(until_year=2026, until_month=6)
        self.assertEqual(len(rows), 2)

        may_balance = round(8.0 - 173.92, 2)
        june_balance = round(0 - 173.92, 2)

        june = rows[0]
        may = rows[1]
        self.assertEqual(may["cumulative_balance"], may_balance)
        self.assertEqual(june["cumulative_balance"], round(may_balance + june_balance, 2))

    def test_rows_newest_first(self):
        self.profile.contract_start_date = date(2026, 5, 1)
        self.profile.save()
        self._make_entry(2026, 5, 10, 9, 17)

        rows = self.profile.get_monthly_account_rows(until_year=2026, until_month=7)
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[0]["month"], 7)
        for i in range(len(rows) - 1):
            self.assertGreater(rows[i]["year"] * 100 + rows[i]["month"],
                               rows[i + 1]["year"] * 100 + rows[i + 1]["month"])

    def test_no_entry_months_included(self):
        self.profile.contract_start_date = date(2026, 5, 1)
        self.profile.save()
        self._make_entry(2026, 5, 10, 9, 17)

        rows = self.profile.get_monthly_account_rows(until_year=2026, until_month=6)
        self.assertEqual(len(rows), 2)
        self.assertIn(rows[0]["month"], (5, 6))
        self.assertIn(rows[1]["month"], (5, 6))
        self.assertNotEqual(rows[0]["month"], rows[1]["month"])
        june_row = next(r for r in rows if r["month"] == 6)
        self.assertEqual(june_row["hours"], 0.0)

    def test_contract_start_excludes_earlier_months(self):
        self.profile.contract_start_date = date(2026, 6, 1)
        self.profile.save()
        self._make_entry(2026, 4, 10, 9, 17)
        self._make_entry(2026, 5, 15, 9, 17)

        rows = self.profile.get_monthly_account_rows(until_year=2026, until_month=7)
        month_nums = {r["month"] for r in rows}
        self.assertNotIn(4, month_nums)
        self.assertNotIn(5, month_nums)
        self.assertIn(6, month_nums)

    def test_contract_end_clamps_later_months(self):
        self.profile.contract_start_date = date(2026, 5, 1)
        self.profile.contract_end_date = date(2026, 6, 15)
        self.profile.save()
        self._make_entry(2026, 5, 10, 9, 17)
        self._make_entry(2026, 7, 5, 9, 17)

        rows = self.profile.get_monthly_account_rows(until_year=2026, until_month=7)
        month_nums = {r["month"] for r in rows}
        self.assertIn(5, month_nums)
        self.assertIn(6, month_nums)
        self.assertNotIn(7, month_nums)

    def test_with_actual_entry_no_contract_start(self):
        self._make_entry(2026, 5, 10, 9, 17)
        rows = self.profile.get_monthly_account_rows(until_year=2027, until_month=3)
        self.assertGreaterEqual(len(rows), 1)
        first_row = rows[0]
        self.assertEqual(first_row["month"], 3)
        self.assertEqual(first_row["year"], 2027)
        self.assertEqual(first_row["hours"], 0.0)
        self.assertIsNotNone(first_row["cumulative_balance"])
