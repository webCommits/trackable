from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

from trackable.core.utils import decimal_to_hours_and_minutes, hours_and_minutes_to_decimal
from trackable.profiles.forms import ProfileForm
from trackable.profiles.models import Profile


User = get_user_model()


class HoursAndMinutesUtilsTest(TestCase):
    def test_hours_and_minutes_to_decimal(self):
        self.assertEqual(hours_and_minutes_to_decimal(4, 20), Decimal("4.3333"))
        self.assertEqual(hours_and_minutes_to_decimal(40, 0), Decimal("40.0000"))
        self.assertEqual(hours_and_minutes_to_decimal(0, 0), Decimal("0.0000"))
        self.assertEqual(hours_and_minutes_to_decimal(0, 30), Decimal("0.5000"))
        self.assertEqual(hours_and_minutes_to_decimal(1, 1), Decimal("1.0167"))

    def test_decimal_to_hours_and_minutes(self):
        self.assertEqual(decimal_to_hours_and_minutes(Decimal("4.3333")), (4, 20))
        self.assertEqual(decimal_to_hours_and_minutes(Decimal("40.0000")), (40, 0))
        self.assertEqual(decimal_to_hours_and_minutes(None), (0, 0))


class ProfileFormTest(TestCase):
    def test_valid_hours_and_minutes(self):
        form = ProfileForm({
            "title": "Dev",
            "position": "Senior",
            "weekly_hours_hours": "4",
            "weekly_hours_minutes": "20",
            "hourly_rate": "50",
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["weekly_hours"], Decimal("4.3333"))

    def test_valid_full_hours(self):
        form = ProfileForm({
            "title": "Dev",
            "position": "Senior",
            "weekly_hours_hours": "40",
            "weekly_hours_minutes": "0",
            "hourly_rate": "50",
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["weekly_hours"], Decimal("40.0000"))

    def test_minutes_optional_defaults_to_zero(self):
        form = ProfileForm({
            "title": "Dev",
            "position": "Senior",
            "weekly_hours_hours": "40",
            "hourly_rate": "50",
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["weekly_hours"], Decimal("40.0000"))

    def test_minutes_too_high(self):
        form = ProfileForm({
            "title": "Dev",
            "position": "Senior",
            "weekly_hours_hours": "4",
            "weekly_hours_minutes": "60",
            "hourly_rate": "50",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("weekly_hours_minutes", form.errors)

    def test_total_hours_too_high(self):
        form = ProfileForm({
            "title": "Dev",
            "position": "Senior",
            "weekly_hours_hours": "100",
            "weekly_hours_minutes": "0",
            "hourly_rate": "50",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("weekly_hours_hours", form.errors)

    def test_hourly_rate_with_comma(self):
        form = ProfileForm({
            "title": "Dev",
            "position": "Senior",
            "weekly_hours_hours": "40",
            "weekly_hours_minutes": "0",
            "hourly_rate": "50,00",
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["hourly_rate"], Decimal("50.00"))

    def test_save_sets_weekly_hours(self):
        user = User.objects.create_user(username="testuser", password="testpass")
        form = ProfileForm({
            "title": "Dev",
            "position": "Senior",
            "address": "",
            "weekly_hours_hours": "4",
            "weekly_hours_minutes": "20",
            "hourly_rate": "50,00",
            "internal_notes": "",
        })
        self.assertTrue(form.is_valid())
        profile = form.save(commit=False)
        profile.user = user
        profile.save()
        self.assertEqual(profile.weekly_hours, Decimal("4.3333"))

    def test_initial_values_from_instance(self):
        user = User.objects.create_user(username="testuser2", password="testpass")
        profile = Profile.objects.create(
            user=user,
            title="Dev",
            position="Senior",
            weekly_hours=Decimal("4.3333"),
            hourly_rate=Decimal("50.0000"),
        )
        form = ProfileForm(instance=profile)
        self.assertEqual(form.initial.get("weekly_hours_hours"), 4)
        self.assertEqual(form.initial.get("weekly_hours_minutes"), 20)
