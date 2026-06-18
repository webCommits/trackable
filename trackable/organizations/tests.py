from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from trackable.organizations.forms import EmployeeCreateForm
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.profiles.models import Profile


User = get_user_model()


class EmployeeCreateFormTest(TestCase):
    def test_valid_hours_and_minutes(self):
        form = EmployeeCreateForm({
            "username": "employee1",
            "email": "employee1@example.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "temp_password": "secret123",
            "temp_password_confirm": "secret123",
            "weekly_hours_hours": "4",
            "weekly_hours_minutes": "20",
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["weekly_hours"], Decimal("4.3333"))

    def test_valid_full_hours(self):
        form = EmployeeCreateForm({
            "username": "employee2",
            "email": "employee2@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "temp_password": "secret123",
            "temp_password_confirm": "secret123",
            "weekly_hours_hours": "40",
            "weekly_hours_minutes": "0",
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["weekly_hours"], Decimal("40.0000"))

    def test_minutes_optional_defaults_to_zero(self):
        form = EmployeeCreateForm({
            "username": "employee3",
            "email": "employee3@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "temp_password": "secret123",
            "temp_password_confirm": "secret123",
            "weekly_hours_hours": "40",
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["weekly_hours"], Decimal("40.0000"))

    def test_minutes_too_high(self):
        form = EmployeeCreateForm({
            "username": "employee4",
            "email": "employee4@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "temp_password": "secret123",
            "temp_password_confirm": "secret123",
            "weekly_hours_hours": "4",
            "weekly_hours_minutes": "60",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("weekly_hours_minutes", form.errors)

    def test_total_hours_too_high(self):
        form = EmployeeCreateForm({
            "username": "employee5",
            "email": "employee5@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "temp_password": "secret123",
            "temp_password_confirm": "secret123",
            "weekly_hours_hours": "100",
            "weekly_hours_minutes": "0",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("weekly_hours_hours", form.errors)

    def test_save_creates_user(self):
        form = EmployeeCreateForm({
            "username": "employee6",
            "email": "employee6@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "temp_password": "secret123",
            "temp_password_confirm": "secret123",
            "weekly_hours_hours": "4",
            "weekly_hours_minutes": "20",
        })
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertEqual(user.username, "employee6")
        self.assertTrue(user.check_password("secret123"))


class EmployeeProfileDetailVacationTest(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="secret"
        )
        self.employee = User.objects.create_user(
            username="employee", email="employee@example.com", password="secret"
        )
        self.organization = Organization.objects.create(
            name="Test Org",
            created_by=self.manager,
            time_tracking_mode="classic",
            holidays_enabled=False,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.manager, role="manager"
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.employee, role="employee"
        )
        self.profile = Profile.objects.create(
            user=self.employee,
            title="Employee Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def _get_context(self):
        from trackable.organizations.views import employee_profile_detail

        request = RequestFactory().get("/")
        request.user = self.manager
        captured = {}

        def mock_render(request, template_name, context, **kwargs):
            captured[template_name] = context
            return HttpResponse("rendered")

        with patch("trackable.organizations.views.render", mock_render):
            response = employee_profile_detail(
                request,
                user_id=self.employee.id,
                profile_id=self.profile.id,
            )

        self.assertEqual(response.status_code, 200)
        return captured["organizations/employee_profile_detail.html"]

    def test_organization_holidays_disabled_in_context(self):
        context = self._get_context()
        self.assertFalse(context["organization"].holidays_enabled)
