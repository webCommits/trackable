from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from datetime import date, time
from trackable.profiles.models import Profile
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.core.models import Holiday
from trackable.timetracking.models import TimeEntry

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
                "weekly_hours": 40,
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
