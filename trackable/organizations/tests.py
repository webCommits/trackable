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


class EmployeeRemoveTest(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="secret"
        )
        self.employee = User.objects.create_user(
            username="employee", email="employee@example.com", password="secret"
        )
        self.other_manager = User.objects.create_user(
            username="othermanager", email="othermanager@example.com", password="secret"
        )
        self.organization = Organization.objects.create(
            name="Test Org",
            created_by=self.manager,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.manager, role="manager"
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.employee, role="employee"
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.other_manager, role="manager"
        )
        self.profile = Profile.objects.create(
            user=self.employee,
            title="Employee Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )
        from datetime import date, time
        from trackable.timetracking.models import TimeEntry

        self.entry = TimeEntry.objects.create(
            profile=self.profile,
            date=date(2024, 6, 1),
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

    def test_manager_can_delete_employee_account_and_data(self):
        self.client.login(username="manager", password="secret")
        response = self.client.post(f"/org/employees/{self.employee.id}/remove/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/org/")
        self.assertFalse(User.objects.filter(username="employee").exists())
        self.assertFalse(Profile.objects.filter(pk=self.profile.pk).exists())
        from trackable.timetracking.models import TimeEntry

        self.assertFalse(TimeEntry.objects.filter(pk=self.entry.pk).exists())

    def test_manager_cannot_delete_self(self):
        self.client.login(username="manager", password="secret")
        response = self.client.post(f"/org/employees/{self.manager.id}/remove/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/org/employees/{self.manager.id}/")
        self.assertTrue(User.objects.filter(username="manager").exists())

    def test_manager_cannot_delete_organization_owner(self):
        # created_by is the manager in setUp; try to delete the owner
        # from another manager account
        self.client.login(username="othermanager", password="secret")
        response = self.client.post(f"/org/employees/{self.manager.id}/remove/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/org/employees/{self.manager.id}/")
        self.assertTrue(User.objects.filter(username="manager").exists())

    def test_manager_cannot_delete_other_manager(self):
        self.client.login(username="manager", password="secret")
        response = self.client.post(f"/org/employees/{self.other_manager.id}/remove/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/org/employees/{self.other_manager.id}/")
        self.assertTrue(User.objects.filter(username="othermanager").exists())

    def test_employee_cannot_delete_other_employee(self):
        other_employee = User.objects.create_user(
            username="otheremployee", email="otheremployee@example.com", password="secret"
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=other_employee, role="employee"
        )
        self.client.login(username="employee", password="secret")
        response = self.client.post(f"/org/employees/{other_employee.id}/remove/")
        # org_manager_required redirects non-managers to home
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/app/")
        self.assertTrue(User.objects.filter(username="otheremployee").exists())
