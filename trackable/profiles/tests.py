from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from trackable.core.utils import decimal_to_hours_and_minutes, hours_and_minutes_to_decimal
from trackable.organizations.models import Organization, OrganizationMembership
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


class ProfileDetailContextTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Dev",
            position="Senior",
            weekly_hours=Decimal("40.0000"),
            hourly_rate=Decimal("50.0000"),
        )

    def _get_context(self, user):
        from trackable.profiles.views import profile_detail

        request = RequestFactory().get("/")
        request.user = user
        captured = {}

        def mock_render(request, template_name, context, **kwargs):
            captured[template_name] = context
            return HttpResponse("rendered")

        with patch("trackable.profiles.views.render", mock_render):
            response = profile_detail(request, pk=self.profile.pk)

        self.assertEqual(response.status_code, 200)
        return captured["profiles/detail.html"]

    def test_user_without_org_can_log_time_and_see_vacation(self):
        context = self._get_context(self.user)
        self.assertTrue(context["can_log_time"])
        self.assertTrue(context["show_vacation"])

    def test_employee_in_restricted_mode_cannot_log_time(self):
        org = Organization.objects.create(
            name="Test Org",
            created_by=self.user,
            time_tracking_mode="restricted",
        )
        OrganizationMembership.objects.create(
            organization=org, user=self.user, role="employee"
        )
        context = self._get_context(self.user)
        self.assertFalse(context["can_log_time"])
        self.assertTrue(context["show_vacation"])

    def test_employee_with_disabled_holidays_cannot_see_vacation(self):
        org = Organization.objects.create(
            name="Test Org",
            created_by=self.user,
            time_tracking_mode="classic",
            holidays_enabled=False,
        )
        OrganizationMembership.objects.create(
            organization=org, user=self.user, role="employee"
        )
        context = self._get_context(self.user)
        self.assertTrue(context["can_log_time"])
        self.assertFalse(context["show_vacation"])
