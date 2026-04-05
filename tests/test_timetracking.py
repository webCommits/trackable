from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import date, time, timedelta
from trackable.profiles.models import Profile
from trackable.timetracking.models import TimeEntry

User = get_user_model()


class TimeEntryModelTest(TestCase):
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

    def test_create_time_entry(self):
        entry = TimeEntry.objects.create(
            profile=self.profile,
            date=date.today(),
            start_time=time(9, 0),
            end_time=time(17, 0),
            pause_duration=1,
        )

        self.assertEqual(entry.profile, self.profile)
        self.assertEqual(entry.hours_worked, 7)

    def test_hours_calculation_no_pause(self):
        entry = TimeEntry.objects.create(
            profile=self.profile,
            date=date.today(),
            start_time=time(9, 0),
            end_time=time(17, 0),
            pause_duration=0,
        )

        self.assertEqual(entry.hours_worked, 8)

    def test_hours_calculation_with_pause(self):
        entry = TimeEntry.objects.create(
            profile=self.profile,
            date=date.today(),
            start_time=time(9, 0),
            end_time=time(17, 30),
            pause_duration=1.5,
        )

        self.assertEqual(entry.hours_worked, 7)

    def test_cross_day_calculation(self):
        entry = TimeEntry.objects.create(
            profile=self.profile,
            date=date.today(),
            start_time=time(22, 0),
            end_time=time(2, 0),
            pause_duration=0,
        )

        self.assertEqual(entry.hours_worked, 4)


class TimeEntryViewTest(TestCase):
    def setUp(self):
        self.client = Client()
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
        self.client.login(username="testuser", password="testpass123")

    def test_add_time_entry(self):
        response = self.client.post(
            reverse("add_entry", kwargs={"profile_id": self.profile.pk}),
            {
                "date": date.today(),
                "start_time": "09:00",
                "end_time": "17:00",
                "pause_duration": 1,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(TimeEntry.objects.filter(profile=self.profile).exists())

    def test_monthly_table(self):
        today = date.today()
        TimeEntry.objects.create(
            profile=self.profile,
            date=today,
            start_time=time(9, 0),
            end_time=time(17, 0),
            pause_duration=1,
        )

        response = self.client.get(
            reverse(
                "monthly_table",
                kwargs={
                    "profile_id": self.profile.pk,
                    "year": today.year,
                    "month": today.month,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Working hours")

    def test_pdf_export(self):
        today = date.today()
        TimeEntry.objects.create(
            profile=self.profile,
            date=today,
            start_time=time(9, 0),
            end_time=time(17, 0),
            pause_duration=1,
        )

        response = self.client.get(
            reverse(
                "export_pdf",
                kwargs={
                    "profile_id": self.profile.pk,
                    "year": today.year,
                    "month": today.month,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
