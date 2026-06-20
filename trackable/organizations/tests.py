from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils import timezone as tz

from trackable.organizations.forms import EmployeeCreateForm
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.profiles.models import Profile
from trackable.timetracking.models import ActiveTimer


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


class OrgDashboardTimerStatusTest(TestCase):
    """Test that org_dashboard shows ActiveTimer status for employees."""

    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="secret"
        )
        self.employee1 = User.objects.create_user(
            username="emp1", email="emp1@example.com", password="secret"
        )
        self.employee2 = User.objects.create_user(
            username="emp2", email="emp2@example.com", password="secret"
        )
        self.employee3 = User.objects.create_user(
            username="emp3", email="emp3@example.com", password="secret"
        )
        self.organization = Organization.objects.create(
            name="Test Org", created_by=self.manager
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.manager, role="manager"
        )
        self.profile1 = Profile.objects.create(
            user=self.employee1, title="Profile 1", position="Dev", weekly_hours=40, hourly_rate=50
        )
        self.profile2 = Profile.objects.create(
            user=self.employee2, title="Profile 2", position="QA", weekly_hours=35, hourly_rate=45
        )
        self.profile3 = Profile.objects.create(
            user=self.employee3, title="Profile 3", position="Design", weekly_hours=30, hourly_rate=40
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.employee1, role="employee"
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.employee2, role="employee"
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.employee3, role="employee"
        )

    def _get_dashboard_context(self):
        from trackable.organizations.views import org_dashboard

        request = RequestFactory().get("/org/")
        request.user = self.manager
        captured = {}

        def mock_render(request, template_name, context, **kwargs):
            captured[template_name] = context
            return HttpResponse("rendered")

        with patch("trackable.organizations.views.render", mock_render):
            response = org_dashboard(request)

        self.assertEqual(response.status_code, 200)
        return captured["organizations/dashboard.html"]

    def _get_employee_detail_context(self, user_id):
        from trackable.organizations.views import employee_detail

        request = RequestFactory().get(f"/org/employees/{user_id}/")
        request.user = self.manager
        captured = {}

        def mock_render(request, template_name, context, **kwargs):
            captured[template_name] = context
            return HttpResponse("rendered")

        with patch("trackable.organizations.views.render", mock_render):
            response = employee_detail(request, user_id=user_id)

        self.assertEqual(response.status_code, 200)
        return captured["organizations/employee_detail.html"]

    def test_running_timer_shown_in_dashboard(self):
        """Manager sees timer status for employee with running timer."""
        ActiveTimer.objects.create(
            profile=self.profile1,
            user=self.employee1,
            start_time=tz.now(),
            is_paused=False,
        )
        context = self._get_dashboard_context()
        emp_memberships = context["employee_memberships"]
        emp1 = next(m for m in emp_memberships if m.user == self.employee1)
        self.assertTrue(emp1.has_running_timer)
        self.assertFalse(emp1.has_paused_timer)
        self.assertEqual(emp1.timer_status, "running")

    def test_paused_timer_shown_in_dashboard(self):
        """Manager sees timer status for employee with paused timer."""
        ActiveTimer.objects.create(
            profile=self.profile2,
            user=self.employee2,
            start_time=tz.now(),
            is_paused=True,
        )
        context = self._get_dashboard_context()
        emp_memberships = context["employee_memberships"]
        emp2 = next(m for m in emp_memberships if m.user == self.employee2)
        self.assertFalse(emp2.has_running_timer)
        self.assertTrue(emp2.has_paused_timer)
        self.assertEqual(emp2.timer_status, "paused")

    def test_no_timer_no_badge(self):
        """Employee without timer has no timer status."""
        context = self._get_dashboard_context()
        emp_memberships = context["employee_memberships"]
        emp3 = next(m for m in emp_memberships if m.user == self.employee3)
        self.assertFalse(emp3.has_running_timer)
        self.assertFalse(emp3.has_paused_timer)
        self.assertIsNone(emp3.timer_status)

    def test_running_priority_over_paused(self):
        """When employee has both running and paused timers (on different profiles), running wins."""
        # Create a second profile for employee1 with a paused timer
        profile1b = Profile.objects.create(
            user=self.employee1, title="Profile 1B", position="Dev2", weekly_hours=40, hourly_rate=50
        )
        ActiveTimer.objects.create(
            profile=self.profile1,
            user=self.employee1,
            start_time=tz.now(),
            is_paused=True,
        )
        ActiveTimer.objects.create(
            profile=profile1b,
            user=self.employee1,
            start_time=tz.now(),
            is_paused=False,
        )
        # employee2 has a paused timer
        ActiveTimer.objects.create(
            profile=self.profile2,
            user=self.employee2,
            start_time=tz.now(),
            is_paused=True,
        )
        context = self._get_dashboard_context()
        emp_memberships = context["employee_memberships"]
        emp1 = next(m for m in emp_memberships if m.user == self.employee1)
        # emp1 has 2 timers: one running (profile1b), one paused (profile1)
        self.assertTrue(emp1.has_running_timer)
        self.assertTrue(emp1.has_paused_timer)
        self.assertEqual(emp1.timer_status, "running")  # running takes priority
        emp2 = next(m for m in emp_memberships if m.user == self.employee2)
        self.assertFalse(emp2.has_running_timer)
        self.assertTrue(emp2.has_paused_timer)
        self.assertEqual(emp2.timer_status, "paused")

    def test_timer_from_other_org_not_shown(self):
        """Timer belonging to a profile not in this org is not shown."""
        # Create a timer on profile3 (which IS in this org) — it should show
        # because profile3 belongs to Test Org via employee3's membership.
        # To test cross-org, create a timer on a profile whose user has NO
        # membership in this org.
        outsider = User.objects.create_user(
            username="outsider", email="outsider@example.com", password="secret"
        )
        outsider_profile = Profile.objects.create(
            user=outsider, title="Outsider Profile", position="Freelancer", weekly_hours=20, hourly_rate=60
        )
        ActiveTimer.objects.create(
            profile=outsider_profile,
            user=outsider,
            start_time=tz.now(),
            is_paused=False,
        )
        context = self._get_dashboard_context()
        # outsider is not in this org, so no membership → no timer visible
        emp_memberships = context["employee_memberships"]
        for m in emp_memberships:
            self.assertFalse(m.has_running_timer or m.has_paused_timer,
                             f"User {m.user.username} should have no timers")


class EmployeeDetailTimerStatusTest(TestCase):
    """Test that employee_detail shows ActiveTimer status per profile."""

    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="secret"
        )
        self.employee = User.objects.create_user(
            username="emp", email="emp@example.com", password="secret"
        )
        self.organization = Organization.objects.create(
            name="Test Org", created_by=self.manager
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.manager, role="manager"
        )
        self.profile1 = Profile.objects.create(
            user=self.employee, title="Profile 1", position="Dev", weekly_hours=40, hourly_rate=50
        )
        self.profile2 = Profile.objects.create(
            user=self.employee, title="Profile 2", position="QA", weekly_hours=35, hourly_rate=45
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.employee, role="employee"
        )

    def _get_employee_detail_context(self):
        return self._get_ctx(f"/org/employees/{self.employee.id}/")

    def _get_ctx(self, url):
        from trackable.organizations.views import employee_detail

        request = RequestFactory().get(url)
        request.user = self.manager
        captured = {}

        def mock_render(request, template_name, context, **kwargs):
            captured[template_name] = context
            return HttpResponse("rendered")

        with patch("trackable.organizations.views.render", mock_render):
            response = employee_detail(request, user_id=self.employee.id)

        self.assertEqual(response.status_code, 200)
        return captured["organizations/employee_detail.html"]

    def test_running_timer_shown_in_employee_detail(self):
        """Employee detail shows running timer for profile with active timer."""
        ActiveTimer.objects.create(
            profile=self.profile1,
            user=self.employee,
            start_time=tz.now(),
            is_paused=False,
        )
        context = self._get_employee_detail_context()
        pd_list = context["profile_data"]
        pd1 = next(p for p in pd_list if p["profile"] == self.profile1)
        self.assertIsNotNone(pd1["active_timer"])
        self.assertFalse(pd1["active_timer"].is_paused)

    def test_paused_timer_shown_in_employee_detail(self):
        """Employee detail shows paused timer for profile with paused timer."""
        ActiveTimer.objects.create(
            profile=self.profile2,
            user=self.employee,
            start_time=tz.now(),
            is_paused=True,
        )
        context = self._get_employee_detail_context()
        pd_list = context["profile_data"]
        pd2 = next(p for p in pd_list if p["profile"] == self.profile2)
        self.assertIsNotNone(pd2["active_timer"])
        self.assertTrue(pd2["active_timer"].is_paused)

    def test_no_timer_no_badge_in_detail(self):
        """Profile without timer has no active_timer in employee detail."""
        context = self._get_employee_detail_context()
        pd_list = context["profile_data"]
        pd1 = next(p for p in pd_list if p["profile"] == self.profile1)
        self.assertIsNone(pd1["active_timer"])
        pd2 = next(p for p in pd_list if p["profile"] == self.profile2)
        self.assertIsNone(pd2["active_timer"])

    def test_multiple_profiles_different_timer_states(self):
        """Multiple profiles show correct timer status per profile."""
        ActiveTimer.objects.create(
            profile=self.profile1,
            user=self.employee,
            start_time=tz.now(),
            is_paused=False,
        )
        ActiveTimer.objects.create(
            profile=self.profile2,
            user=self.employee,
            start_time=tz.now(),
            is_paused=True,
        )
        context = self._get_employee_detail_context()
        pd_list = context["profile_data"]
        pd1 = next(p for p in pd_list if p["profile"] == self.profile1)
        pd2 = next(p for p in pd_list if p["profile"] == self.profile2)
        self.assertIsNotNone(pd1["active_timer"])
        self.assertFalse(pd1["active_timer"].is_paused)
        self.assertIsNotNone(pd2["active_timer"])
        self.assertTrue(pd2["active_timer"].is_paused)
