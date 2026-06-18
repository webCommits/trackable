from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from trackable.organizations.helpers import can_manage_profile_time_entries
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.profiles.models import Profile
from trackable.timetracking.models import TimeEntry, VacationEntry


User = get_user_model()


class ManagerTimeEntryFormTest(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="secret"
        )
        self.employee = User.objects.create_user(
            username="employee", email="employee@example.com", password="secret"
        )
        self.other_user = User.objects.create_user(
            username="other", email="other@example.com", password="secret"
        )

        self.organization = Organization.objects.create(
            name="Test Org",
            created_by=self.manager,
            time_tracking_mode="restricted",
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.manager, role="manager"
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.employee, role="employee"
        )

        self.other_org = Organization.objects.create(
            name="Other Org",
            created_by=self.other_user,
            time_tracking_mode="restricted",
        )
        OrganizationMembership.objects.create(
            organization=self.other_org, user=self.other_user, role="manager"
        )

        self.profile = Profile.objects.create(
            user=self.employee,
            title="Employee Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )
        self.other_profile = Profile.objects.create(
            user=self.other_user,
            title="Other Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def test_manager_can_add_entry_for_employee_in_restricted_mode(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            f"/add-entry/{self.profile.id}/",
            {
                "date": "2024-06-18",
                "start_time": "08:00",
                "end_time": "16:00",
                "pause_duration": "1",
                "notes": "Test entry",
            },
        )
        self.assertEqual(TimeEntry.objects.count(), 1)
        entry = TimeEntry.objects.first()
        self.assertEqual(entry.profile, self.profile)
        self.assertEqual(entry.hours_worked, 7)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse(
                "employee_profile_detail",
                kwargs={"user_id": self.employee.id, "profile_id": self.profile.id},
            ),
        )

    def test_manager_can_edit_entry_for_employee(self):
        entry = TimeEntry.objects.create(
            profile=self.profile,
            date=date(2024, 6, 18),
            start_time=time(8, 0),
            end_time=time(12, 0),
            pause_duration=0,
            hours_worked=4,
        )
        self.client.force_login(self.manager)
        response = self.client.post(
            f"/entry/{entry.id}/edit/",
            {
                "date": "2024-06-18",
                "start_time": "08:00",
                "end_time": "14:00",
                "pause_duration": "0",
                "notes": "Updated",
            },
        )
        entry.refresh_from_db()
        self.assertEqual(entry.hours_worked, 6)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse(
                "employee_profile_detail",
                kwargs={"user_id": self.employee.id, "profile_id": self.profile.id},
            ),
        )

    def test_manager_can_delete_entry_for_employee(self):
        entry = TimeEntry.objects.create(
            profile=self.profile,
            date=date(2024, 6, 18),
            start_time=time(8, 0),
            end_time=time(12, 0),
            pause_duration=0,
            hours_worked=4,
        )
        self.client.force_login(self.manager)
        response = self.client.post(f"/entry/{entry.id}/delete/")
        self.assertEqual(TimeEntry.objects.count(), 0)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse(
                "employee_profile_detail",
                kwargs={"user_id": self.employee.id, "profile_id": self.profile.id},
            ),
        )

    def test_employee_cannot_add_entry_in_restricted_mode(self):
        self.client.force_login(self.employee)
        response = self.client.post(
            f"/add-entry/{self.profile.id}/",
            {
                "date": "2024-06-18",
                "start_time": "08:00",
                "end_time": "16:00",
                "pause_duration": "1",
                "notes": "Test entry",
            },
        )
        self.assertEqual(TimeEntry.objects.count(), 0)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_manager_cannot_access_profile_from_other_organization(self):
        self.client.force_login(self.manager)
        response = self.client.get(f"/add-entry/{self.other_profile.id}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_helper_can_manage_profile_time_entries(self):
        self.assertTrue(can_manage_profile_time_entries(self.manager, self.profile))
        self.assertFalse(
            can_manage_profile_time_entries(self.employee, self.profile)
        )
        self.assertFalse(
            can_manage_profile_time_entries(self.manager, self.other_profile)
        )


class VacationDisabledTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="employee", email="employee@example.com", password="secret"
        )
        self.organization = Organization.objects.create(
            name="Test Org",
            created_by=self.user,
            time_tracking_mode="classic",
            holidays_enabled=False,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.user, role="employee"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Employee Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def test_vacation_overview_redirects_when_disabled(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/vacation/{self.profile.id}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_add_vacation_redirects_when_disabled(self):
        self.client.force_login(self.user)
        response = self.client.post(
            f"/vacation/{self.profile.id}/add/",
            {
                "start_date": "2024-06-18",
                "end_date": "2024-06-20",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertEqual(VacationEntry.objects.count(), 0)

    def test_delete_vacation_redirects_when_disabled(self):
        vacation = VacationEntry.objects.create(
            profile=self.profile,
            start_date=date(2024, 6, 18),
            end_date=date(2024, 6, 20),
        )
        self.client.force_login(self.user)
        response = self.client.post(f"/vacation/delete/{vacation.id}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertEqual(VacationEntry.objects.count(), 1)


class MonthlyTableVacationButtonTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="employee", email="employee@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Employee Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def _get_context(self, user):
        from trackable.timetracking.views import monthly_table

        request = RequestFactory().get("/")
        request.user = user
        captured = {}

        def mock_render(request, template_name, context, **kwargs):
            captured[template_name] = context
            return HttpResponse("rendered")

        with patch("trackable.timetracking.views.render", mock_render):
            response = monthly_table(request, profile_id=self.profile.id, year=2024, month=6)

        self.assertEqual(response.status_code, 200)
        return captured["timetracking/monthly_table.html"]

    def test_user_without_org_sees_vacation_button(self):
        context = self._get_context(self.user)
        self.assertTrue(context["show_vacation"])

    def test_user_with_disabled_holidays_does_not_see_vacation_button(self):
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
        self.assertFalse(context["show_vacation"])
