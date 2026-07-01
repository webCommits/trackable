from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.core.models import Holiday
from trackable.profiles.models import AVERAGE_WEEKS_PER_MONTH, Profile, TARGET_HOURS_MONTHLY
from trackable.timetracking.models import VacationEntry
from datetime import date, time

User = get_user_model()


class OrganizationModelTest(TestCase):
    def test_create_organization_auto_slug(self):
        user = User.objects.create_user(username="owner", password="pass123")
        org = Organization.objects.create(name="Acme Corp", created_by=user)
        self.assertEqual(org.slug, "acme-corp")

    def test_slug_uniqueness(self):
        user = User.objects.create_user(username="owner", password="pass123")
        Organization.objects.create(name="Acme Corp", created_by=user)
        org2 = Organization.objects.create(name="Acme Corp", created_by=user)
        self.assertNotEqual(org2.slug, "acme-corp")
        self.assertTrue(org2.slug.startswith("acme-corp-"))

    def test_membership_str(self):
        user = User.objects.create_user(username="owner", password="pass123")
        org = Organization.objects.create(name="Acme Corp", created_by=user)
        membership = OrganizationMembership.objects.create(
            organization=org, user=user, role="manager"
        )
        self.assertIn("Manager", str(membership))
        self.assertIn("Acme Corp", str(membership))

    def test_is_manager_property(self):
        user = User.objects.create_user(username="owner", password="pass123")
        org = Organization.objects.create(name="Acme Corp", created_by=user)
        m = OrganizationMembership.objects.create(
            organization=org, user=user, role="manager"
        )
        self.assertTrue(m.is_manager)

        user2 = User.objects.create_user(username="emp", password="pass123")
        m2 = OrganizationMembership.objects.create(
            organization=org, user=user2, role="employee"
        )
        self.assertFalse(m2.is_manager)


class OrganizationViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="pass123"
        )
        self.org = Organization.objects.create(
            name="Acme Corp", created_by=self.manager
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.org, user=self.manager, role="manager"
        )
        self.client.login(username="manager", password="pass123")

    def test_org_create(self):
        new_user = User.objects.create_user(
            username="newmgr", email="new@example.com", password="pass123"
        )
        self.client.login(username="newmgr", password="pass123")
        response = self.client.post(reverse("org_create"), {"name": "New Org"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Organization.objects.filter(name="New Org").exists())
        membership = OrganizationMembership.objects.get(user=new_user)
        self.assertEqual(membership.role, "manager")

    def test_org_dashboard_manager(self):
        response = self.client.get(reverse("org_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acme Corp")

    def test_org_dashboard_employee(self):
        employee = User.objects.create_user(
            username="employee", email="emp@example.com", password="pass123"
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=employee, role="employee"
        )
        self.client.login(username="employee", password="pass123")
        response = self.client.get(reverse("org_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_employee_create(self):
        response = self.client.post(
            reverse("employee_create"),
            {
                "username": "newemp",
                "email": "newemp@example.com",
                "first_name": "New",
                "last_name": "Employee",
                "temp_password": "temppass123",
                "temp_password_confirm": "temppass123",
                "weekly_hours_hours": "40",
                "weekly_hours_minutes": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="newemp")
        self.assertTrue(user.email_confirmed)
        membership = OrganizationMembership.objects.get(user=user)
        self.assertEqual(membership.role, "employee")
        self.assertEqual(membership.organization, self.org)

    def test_employee_create_with_contract_dates(self):
        response = self.client.post(
            reverse("employee_create"),
            {
                "username": "contremp",
                "email": "contremp@example.com",
                "first_name": "Contract",
                "last_name": "Emp",
                "temp_password": "temppass123",
                "temp_password_confirm": "temppass123",
                "weekly_hours_hours": "35",
                "weekly_hours_minutes": "0",
                "contract_start_date": "2026-06-01",
                "contract_end_date": "2026-12-31",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="contremp")
        profile = user.profiles.first()
        self.assertIsNotNone(profile)
        self.assertEqual(float(profile.weekly_hours), 35.0)
        self.assertEqual(profile.contract_start_date.isoformat(), "2026-06-01")
        self.assertEqual(profile.contract_end_date.isoformat(), "2026-12-31")

    def test_employee_create_with_monthly_target_hours(self):
        response = self.client.post(
            reverse("employee_create"),
            {
                "username": "monthlyemp",
                "email": "monthlyemp@example.com",
                "first_name": "Monthly",
                "last_name": "Emp",
                "temp_password": "temppass123",
                "temp_password_confirm": "temppass123",
                "target_hours_period": TARGET_HOURS_MONTHLY,
                "monthly_target_hours_hours": "78",
                "monthly_target_hours_minutes": "15",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="monthlyemp")
        profile = user.profiles.first()
        self.assertEqual(profile.target_hours_period, TARGET_HOURS_MONTHLY)
        self.assertEqual(float(profile.monthly_target_hours), 78.25)
        self.assertAlmostEqual(
            float(profile.weekly_hours),
            78.25 / AVERAGE_WEEKS_PER_MONTH,
            places=3,
        )

    def test_employee_create_end_before_start_fails(self):
        response = self.client.post(
            reverse("employee_create"),
            {
                "username": "bademp",
                "email": "bademp@example.com",
                "first_name": "Bad",
                "last_name": "Emp",
                "temp_password": "temppass123",
                "temp_password_confirm": "temppass123",
                "weekly_hours_hours": "40",
                "weekly_hours_minutes": "0",
                "contract_start_date": "2026-12-01",
                "contract_end_date": "2026-06-01",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Contract end date must be after start date")

    def test_employee_create_without_contract_dates(self):
        """Contract dates are optional – create employee without them."""
        response = self.client.post(
            reverse("employee_create"),
            {
                "username": "noctremp",
                "email": "noctremp@example.com",
                "first_name": "No",
                "last_name": "Contract",
                "temp_password": "temppass123",
                "temp_password_confirm": "temppass123",
                "weekly_hours_hours": "40",
                "weekly_hours_minutes": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="noctremp")
        profile = user.profiles.first()
        self.assertIsNotNone(profile)
        self.assertIsNone(profile.contract_start_date)
        self.assertIsNone(profile.contract_end_date)

    def test_employee_detail(self):
        employee = User.objects.create_user(
            username="employee", email="emp@example.com", password="pass123"
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=employee, role="employee"
        )
        response = self.client.get(
            reverse("employee_detail", kwargs={"user_id": employee.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "employee")

    def test_employee_remove(self):
        employee = User.objects.create_user(
            username="employee", email="emp@example.com", password="pass123"
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=employee, role="employee"
        )
        Profile.objects.create(
            user=employee,
            title="Employee Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )
        response = self.client.post(
            reverse("employee_remove", kwargs={"user_id": employee.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username="employee").exists())
        self.assertFalse(Profile.objects.filter(user=employee).exists())

    def test_non_manager_cannot_create_employee(self):
        employee = User.objects.create_user(
            username="employee", email="emp@example.com", password="pass123"
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=employee, role="employee"
        )
        self.client.login(username="employee", password="pass123")
        response = self.client.get(reverse("employee_create"))
        self.assertEqual(response.status_code, 302)

    def test_is_org_manager_property(self):
        self.assertTrue(self.manager.is_org_manager)
        employee = User.objects.create_user(
            username="employee", email="emp@example.com", password="pass123"
        )
        self.assertFalse(employee.is_org_manager)

    def test_org_create_redirects_if_already_member(self):
        response = self.client.get(reverse("org_create"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_shows_org_button_for_user_without_org(self):
        user = User.objects.create_user(username="loner", password="pass123")
        self.client.login(username="loner", password="pass123")
        Profile.objects.create(
            user=user, title="Dev", position="Dev", weekly_hours=40, hourly_rate=50
        )
        response = self.client.get(reverse("home"))
        self.assertContains(response, "New organization")


class OrganizationHolidayTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="pass123"
        )
        self.org = Organization.objects.create(
            name="Acme Corp", created_by=self.manager
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.org, user=self.manager, role="manager"
        )
        self.client.login(username="manager", password="pass123")

    def test_holiday_list(self):
        Holiday.objects.create(
            date=date(2026, 12, 25), name="Christmas", organization=self.org
        )
        response = self.client.get(reverse("org_holidays"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Christmas")

    def test_holiday_create(self):
        response = self.client.post(
            reverse("org_holiday_add"),
            {"date": "2026-12-25", "name": "Christmas"},
        )
        self.assertEqual(response.status_code, 302)
        holiday = Holiday.objects.get(organization=self.org)
        self.assertEqual(holiday.name, "Christmas")
        self.assertEqual(holiday.organization, self.org)

    def test_holiday_delete(self):
        holiday = Holiday.objects.create(
            date=date(2026, 12, 25), name="Christmas", organization=self.org
        )
        response = self.client.post(
            reverse("org_holiday_delete", kwargs={"pk": holiday.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Holiday.objects.filter(pk=holiday.pk).exists())

    def test_non_manager_cannot_access_holidays(self):
        employee = User.objects.create_user(
            username="employee", email="emp@example.com", password="pass123"
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=employee, role="employee"
        )
        self.client.login(username="employee", password="pass123")
        response = self.client.get(reverse("org_holidays"))
        self.assertEqual(response.status_code, 302)

    def test_vacation_uses_org_holidays(self):
        Holiday.objects.create(
            date=date(2025, 1, 1), name="New Year", organization=self.org
        )
        employee = User.objects.create_user(
            username="employee", email="emp@example.com", password="pass123"
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=employee, role="employee"
        )
        profile = Profile.objects.create(
            user=employee, title="Dev", position="Dev", weekly_hours=40, hourly_rate=50
        )
        vacation = VacationEntry.objects.create(
            profile=profile,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 3),
        )
        self.assertEqual(vacation.workdays, 2)

    def test_vacation_uses_global_holidays_when_no_org(self):
        user = User.objects.create_user(username="loner", password="pass123")
        Holiday.objects.create(
            date=date(2025, 1, 1), name="New Year", organization=None
        )
        profile = Profile.objects.create(
            user=user, title="Dev", position="Dev", weekly_hours=40, hourly_rate=50
        )
        vacation = VacationEntry.objects.create(
            profile=profile,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 3),
        )
        self.assertEqual(vacation.workdays, 2)


class TimeTrackingModeTest(TestCase):
    """Tests for time-tracking mode (classic/restricted)."""

    def setUp(self):
        self.client = Client()
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="pass123"
        )
        self.org = Organization.objects.create(
            name="Acme Corp", created_by=self.manager
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.org, user=self.manager, role="manager"
        )
        self.employee = User.objects.create_user(
            username="employee", email="emp@example.com", password="pass123"
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=self.employee, role="employee"
        )
        self.client.login(username="manager", password="pass123")

    def test_time_tracking_mode_default_classic(self):
        """New organizations start with time_tracking_mode='classic'."""
        self.assertEqual(self.org.time_tracking_mode, "classic")

    def test_toggle_time_tracking_mode_as_manager(self):
        """Manager can toggle time-tracking mode between classic and restricted."""
        # Toggle ON (classic -> restricted)
        response = self.client.post(reverse("toggle_time_tracking_mode"))
        self.assertEqual(response.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.time_tracking_mode, "restricted")

        # Toggle OFF (restricted -> classic)
        response = self.client.post(reverse("toggle_time_tracking_mode"))
        self.assertEqual(response.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.time_tracking_mode, "classic")

    def test_toggle_time_tracking_mode_as_employee_denied(self):
        """Employee cannot toggle time-tracking mode (redirected)."""
        self.client.login(username="employee", password="pass123")
        response = self.client.post(reverse("toggle_time_tracking_mode"))
        self.assertEqual(response.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.time_tracking_mode, "classic")  # unchanged

    def test_weekly_calendar_returns_200(self):
        """Weekly calendar view returns 200 for manager."""
        response = self.client.get(reverse("org_weekly_calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acme Corp")

    def test_weekly_calendar_specific_week(self):
        """Weekly calendar accepts week query params."""
        from datetime import datetime as dt
        today = dt.now().date()
        iso = today.isocalendar()
        response = self.client.get(
            f"{reverse('org_weekly_calendar')}?year={iso[0]}&week={iso[1]}"
        )
        self.assertEqual(response.status_code, 200)

    def test_weekly_calendar_redirects_if_no_org(self):
        """User without org is redirected to org_create."""
        loner = User.objects.create_user(username="loner", password="pass123")
        self.client.login(username="loner", password="pass123")
        response = self.client.get(reverse("org_weekly_calendar"))
        self.assertEqual(response.status_code, 302)

    def test_weekly_calendar_shows_entries(self):
        """Calendar shows time entries for employees in the week."""
        from datetime import datetime as dt, timedelta
        import calendar

        today = dt.now().date()
        monday = today - timedelta(days=today.weekday())

        profile = Profile.objects.create(
            user=self.employee,
            title="Dev",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        TimeEntry.objects.create(
            profile=profile,
            date=monday,
            start_time=dt.now().time(),
            end_time=(dt.now() + timedelta(hours=8)).time(),
            pause_duration=1,
        )

        iso = monday.isocalendar()
        response = self.client.get(
            f"{reverse('org_weekly_calendar')}?year={iso[0]}&week={iso[1]}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dev")

    def test_move_entry_as_manager(self):
        """Manager can move an entry to a different day."""
        from datetime import datetime as dt, timedelta

        today = dt.now().date()
        profile = Profile.objects.create(
            user=self.employee,
            title="Dev",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        entry = TimeEntry.objects.create(
            profile=profile,
            date=today,
            start_time=dt.now().time(),
            end_time=(dt.now() + timedelta(hours=8)).time(),
            pause_duration=1,
        )

        new_date = (today + timedelta(days=1)).isoformat()
        response = self.client.post(
            reverse("move_entry", kwargs={"entry_id": entry.pk}),
            {"new_date": new_date},
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})
        entry.refresh_from_db()
        self.assertEqual(entry.date.isoformat(), new_date)

    def test_move_entry_as_employee_own_entry(self):
        """Employee can move their own entries."""
        from datetime import datetime as dt, timedelta

        today = dt.now().date()
        profile = Profile.objects.create(
            user=self.employee,
            title="Dev",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        entry = TimeEntry.objects.create(
            profile=profile,
            date=today,
            start_time=dt.now().time(),
            end_time=(dt.now() + timedelta(hours=8)).time(),
            pause_duration=1,
        )

        self.client.login(username="employee", password="pass123")
        new_date = (today + timedelta(days=1)).isoformat()
        response = self.client.post(
            reverse("move_entry", kwargs={"entry_id": entry.pk}),
            {"new_date": new_date},
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})
        entry.refresh_from_db()
        self.assertEqual(entry.date.isoformat(), new_date)

    def test_move_entry_as_employee_other_entry_allowed(self):
        """Employees can move any entry in their organization."""
        from datetime import datetime as dt, timedelta

        today = dt.now().date()
        other_employee = User.objects.create_user(
            username="other_employee", email="other@example.com", password="pass123"
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=other_employee, role="employee"
        )
        profile = Profile.objects.create(
            user=other_employee,
            title="Dev",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        entry = TimeEntry.objects.create(
            profile=profile,
            date=today,
            start_time=dt.now().time(),
            end_time=(dt.now() + timedelta(hours=8)).time(),
            pause_duration=1,
        )

        self.client.login(username="employee", password="pass123")
        new_date = (today + timedelta(days=1)).isoformat()
        response = self.client.post(
            reverse("move_entry", kwargs={"entry_id": entry.pk}),
            {"new_date": new_date},
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})
        entry.refresh_from_db()
        self.assertEqual(entry.date.isoformat(), new_date)

    def test_delete_entry_as_manager(self):
        """Manager can delete any entry in the organization."""
        from datetime import datetime as dt, timedelta

        today = dt.now().date()
        profile = Profile.objects.create(
            user=self.employee,
            title="Dev",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        entry = TimeEntry.objects.create(
            profile=profile,
            date=today,
            start_time=dt.now().time(),
            end_time=(dt.now() + timedelta(hours=8)).time(),
            pause_duration=1,
        )

        response = self.client.post(
            reverse("delete_calendar_entry", kwargs={"entry_id": entry.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})
        self.assertFalse(TimeEntry.objects.filter(pk=entry.pk).exists())

    def test_delete_entry_as_employee_own(self):
        """Employee can delete their own entries."""
        from datetime import datetime as dt, timedelta

        today = dt.now().date()
        profile = Profile.objects.create(
            user=self.employee,
            title="Dev",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        entry = TimeEntry.objects.create(
            profile=profile,
            date=today,
            start_time=dt.now().time(),
            end_time=(dt.now() + timedelta(hours=8)).time(),
            pause_duration=1,
        )

        self.client.login(username="employee", password="pass123")
        response = self.client.post(
            reverse("delete_calendar_entry", kwargs={"entry_id": entry.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})
        self.assertFalse(TimeEntry.objects.filter(pk=entry.pk).exists())

    def test_delete_entry_as_employee_other_denied(self):
        """Employee cannot delete another employee's entries."""
        from datetime import datetime as dt, timedelta

        today = dt.now().date()
        other_employee = User.objects.create_user(
            username="other_employee", email="other@example.com", password="pass123"
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=other_employee, role="employee"
        )
        profile = Profile.objects.create(
            user=other_employee,
            title="Dev",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        entry = TimeEntry.objects.create(
            profile=profile,
            date=today,
            start_time=dt.now().time(),
            end_time=(dt.now() + timedelta(hours=8)).time(),
            pause_duration=1,
        )

        self.client.login(username="employee", password="pass123")
        response = self.client.post(
            reverse("delete_calendar_entry", kwargs={"entry_id": entry.pk}),
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(TimeEntry.objects.filter(pk=entry.pk).exists())

    def test_delete_entry_not_org_member(self):
        """A user outside the organization cannot delete entries."""
        from datetime import datetime as dt, timedelta

        today = dt.now().date()
        profile = Profile.objects.create(
            user=self.employee,
            title="Dev",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        entry = TimeEntry.objects.create(
            profile=profile,
            date=today,
            start_time=dt.now().time(),
            end_time=(dt.now() + timedelta(hours=8)).time(),
            pause_duration=1,
        )

        outsider = User.objects.create_user(
            username="outsider", email="outsider@example.com", password="pass123"
        )
        self.client.login(username="outsider", password="pass123")
        response = self.client.post(
            reverse("delete_calendar_entry", kwargs={"entry_id": entry.pk}),
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(TimeEntry.objects.filter(pk=entry.pk).exists())

    def test_move_entry_not_org_member(self):
        """A user outside the organization cannot move entries."""
        from datetime import datetime as dt, timedelta

        today = dt.now().date()
        profile = Profile.objects.create(
            user=self.employee,
            title="Dev",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        entry = TimeEntry.objects.create(
            profile=profile,
            date=today,
            start_time=dt.now().time(),
            end_time=(dt.now() + timedelta(hours=8)).time(),
            pause_duration=1,
        )

        outsider = User.objects.create_user(
            username="outsider", email="outsider@example.com", password="pass123"
        )
        self.client.login(username="outsider", password="pass123")
        new_date = (today + timedelta(days=1)).isoformat()
        response = self.client.post(
            reverse("move_entry", kwargs={"entry_id": entry.pk}),
            {"new_date": new_date},
        )
        self.assertEqual(response.status_code, 403)
        entry.refresh_from_db()
        self.assertEqual(entry.date, today)


# Make TimeEntry available for tests above
from trackable.timetracking.models import (
    ENTRY_TYPE_ACTUAL,
    ENTRY_TYPE_PLANNED,
    TimeEntry,
)


class SetTargetHoursTest(TestCase):
    """Tests for the set_target_hours manager view."""

    def setUp(self):
        self.client = Client()
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="pass123"
        )
        self.employee = User.objects.create_user(
            username="employee", email="emp@example.com", password="pass123"
        )
        self.org = Organization.objects.create(
            name="Acme Corp", created_by=self.manager
        )
        self.manager_membership = OrganizationMembership.objects.create(
            user=self.manager, organization=self.org, role="manager"
        )
        self.employee_membership = OrganizationMembership.objects.create(
            user=self.employee, organization=self.org, role="employee"
        )
        self.profile = Profile.objects.create(
            user=self.employee,
            title="Dev",
            position="Engineer",
            weekly_hours=40,
            hourly_rate=50,
        )

    def test_set_target_hours_requires_login(self):
        response = self.client.post(
            reverse("set_target_hours", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
            {"weekly_target_hours": "30"},
        )
        self.assertRedirects(
            response,
            f"/accounts/login/?next=/org/employees/{self.employee.id}/profiles/{self.profile.id}/set-target-hours/",
        )

    def test_set_target_hours_requires_manager(self):
        self.client.login(username="employee", password="pass123")
        response = self.client.post(
            reverse("set_target_hours", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
            {"weekly_target_hours_hours": "30", "weekly_target_hours_minutes": "0"},
        )
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.weekly_target_hours)

    def test_set_target_hours_saves_value(self):
        self.client.login(username="manager", password="pass123")
        response = self.client.post(
            reverse("set_target_hours", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
            {"weekly_target_hours_hours": "30", "weekly_target_hours_minutes": "0"},
        )
        self.assertRedirects(
            response,
            reverse("employee_profile_detail", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
        )
        self.profile.refresh_from_db()
        self.assertEqual(float(self.profile.weekly_target_hours), 30.0)

    def test_set_target_hours_saves_monthly_value(self):
        self.client.login(username="manager", password="pass123")
        response = self.client.post(
            reverse("set_target_hours", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
            {
                "target_hours_period": TARGET_HOURS_MONTHLY,
                "monthly_target_hours_hours": "78",
                "monthly_target_hours_minutes": "15",
            },
        )
        self.assertRedirects(
            response,
            reverse("employee_profile_detail", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.target_hours_period, TARGET_HOURS_MONTHLY)
        self.assertEqual(float(self.profile.monthly_target_hours), 78.25)
        self.assertIsNone(self.profile.weekly_target_hours)
        self.assertEqual(self.profile.get_target_hours(2026, 5), 78.25)

    def test_set_target_hours_switches_monthly_back_to_weekly(self):
        self.profile.target_hours_period = TARGET_HOURS_MONTHLY
        self.profile.monthly_target_hours = 78.25
        self.profile.save()
        self.client.login(username="manager", password="pass123")

        response = self.client.post(
            reverse("set_target_hours", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
            {
                "target_hours_period": "weekly",
                "weekly_target_hours_hours": "18",
                "weekly_target_hours_minutes": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.target_hours_period, "weekly")
        self.assertIsNone(self.profile.monthly_target_hours)
        self.assertEqual(float(self.profile.weekly_target_hours), 18.0)
        self.assertEqual(self.profile.get_target_hours(2026, 5), 78.26)

    def test_set_target_hours_clears_to_none(self):
        self.profile.weekly_target_hours = 30
        self.profile.save()
        self.client.login(username="manager", password="pass123")
        response = self.client.post(
            reverse("set_target_hours", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
            {"weekly_target_hours_hours": "", "weekly_target_hours_minutes": ""},
        )
        self.assertRedirects(
            response,
            reverse("employee_profile_detail", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
        )
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.weekly_target_hours)

    def test_set_target_hours_wrong_org_manager_cant_set(self):
        """Manager of org A cannot set target hours on employee of org B."""
        other_mgr = User.objects.create_user(
            username="othermgr", password="pass123"
        )
        other_org = Organization.objects.create(name="Other Corp", slug="other", created_by=other_mgr)
        OrganizationMembership.objects.create(
            user=other_mgr, organization=other_org, role="manager"
        )
        self.client.login(username="othermgr", password="pass123")
        response = self.client.post(
            reverse("set_target_hours", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
            {"weekly_target_hours_hours": "30", "weekly_target_hours_minutes": "0"},
        )
        self.assertEqual(response.status_code, 404)

    def test_set_target_hours_updates_target_calculation(self):
        """After setting weekly_target_hours=30, get_target_hours should use it."""
        self.client.login(username="manager", password="pass123")
        self.client.post(
            reverse("set_target_hours", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
            {"weekly_target_hours_hours": "30", "weekly_target_hours_minutes": "0"},
        )
        self.profile.refresh_from_db()
        target = self.profile.get_target_hours(2026, 5)
        self.assertEqual(target, 130.44)  # 30 × 4,348 = 130,44


class OrganizationBrandingTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.manager = User.objects.create_user(
            username="brandmgr", password="pass123",
        )
        self.org = Organization.objects.create(
            name="BrandCorp", slug="brandcorp",
            created_by=self.manager,
        )
        OrganizationMembership.objects.create(
            user=self.manager, organization=self.org, role="manager",
        )
        self.client.login(username="brandmgr", password="pass123")

    def test_branding_view_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("org_branding"))
        self.assertEqual(resp.status_code, 302)

    def test_branding_view_requires_manager(self):
        emp = User.objects.create_user(username="brandemp", password="pass123")
        OrganizationMembership.objects.create(
            user=emp, organization=self.org, role="employee",
        )
        self.client.login(username="brandemp", password="pass123")
        resp = self.client.get(reverse("org_branding"))
        # org_manager_required decorator redirects to "home"
        self.assertEqual(resp.status_code, 302)

    def test_branding_view_renders_200(self):
        resp = self.client.get(reverse("org_branding"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Company Branding")

    def test_branding_saves_colors(self):
        resp = self.client.post(reverse("org_branding"), {
            "primary_color": "#ff0000",
            "accent_color": "#00ff00",
            "custom_css": ".btn { background: red !important; }",
        })
        self.assertEqual(resp.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.primary_color, "#ff0000")
        self.assertEqual(self.org.accent_color, "#00ff00")
        self.assertEqual(self.org.custom_css, ".btn { background: red !important; }")

    def test_branding_defaults_empty(self):
        self.org.refresh_from_db()
        self.assertEqual(self.org.primary_color, "")
        self.assertEqual(self.org.accent_color, "")
        self.assertEqual(self.org.custom_css, "")

    def test_context_processor_no_org(self):
        user = User.objects.create_user(username="noorg", password="pass123")
        Profile.objects.create(
            user=user, title="Test", position="X",
            weekly_hours=40, hourly_rate=0,
        )
        self.client.login(username="noorg", password="pass123")
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context.get("has_branding"))

    def test_branding_logo_url_in_context(self):
        """Test that setting a logo makes org_logo_url available."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        import io
        from PIL import Image

        img = io.BytesIO()
        Image.new("RGBA", (180, 40), (136, 57, 239, 255)).save(img, "PNG")
        img.seek(0)
        self.org.logo = SimpleUploadedFile(
            "test_logo.png", img.getvalue(), content_type="image/png"
        )
        self.org.save()

        resp = self.client.get(reverse("org_dashboard"))
        self.assertContains(resp, self.org.logo.url)


class WeeklyCalendarEntryTest(TestCase):
    """Tests for weekly calendar entry creation (planned vs actual)."""

    def setUp(self):
        self.client = Client()
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="pass123"
        )
        self.org = Organization.objects.create(
            name="Acme Corp", created_by=self.manager
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.org, user=self.manager, role="manager"
        )
        self.employee = User.objects.create_user(
            username="employee", email="emp@example.com", password="pass123"
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=self.employee, role="employee"
        )
        self.profile = Profile.objects.create(
            user=self.employee,
            title="Dev",
            position="Developer",
            weekly_hours=40,
            hourly_rate=50,
        )
        self.client.login(username="manager", password="pass123")

    def test_create_entry_from_weekly_calendar_is_planned(self):
        """POST to create_entry should create a planned entry."""
        response = self.client.post(
            reverse("create_entry"),
            {
                "profile_id": self.profile.id,
                "date": "2026-07-15",
                "start_time": "09:00",
                "end_time": "17:00",
                "notes": "Test planned entry",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        entry = TimeEntry.objects.get(pk=data["entry"]["id"])
        self.assertEqual(entry.entry_type, ENTRY_TYPE_PLANNED)

    def test_planned_entry_does_not_affect_employee_detail_balance(self):
        """A planned entry should not affect the employee profile detail total hours/balance."""
        self.client.post(
            reverse("create_entry"),
            {
                "profile_id": self.profile.id,
                "date": "2026-07-15",
                "start_time": "09:00",
                "end_time": "17:00",
                "notes": "Planned",
            },
        )
        resp = self.client.get(
            reverse("employee_profile_detail", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            })
        )
        self.assertEqual(resp.status_code, 200)
        # Total hours should be 0 (planned entries excluded)
        self.assertEqual(resp.context["total_hours"], 0)
        # Balance should equal negative target hours
        balance = resp.context["balance"]
        target = resp.context["target_hours"]
        self.assertAlmostEqual(balance, -target, places=2)

    def test_actual_entry_still_affects_employee_detail(self):
        """An actual entry should still affect the employee profile detail."""
        from datetime import datetime
        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 7, 15),
            start_time=datetime.strptime("09:00", "%H:%M").time(),
            end_time=datetime.strptime("17:00", "%H:%M").time(),
            entry_type=ENTRY_TYPE_ACTUAL,
        )
        resp = self.client.get(
            reverse("employee_profile_detail", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            })
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_hours"], 8.0)

    def test_employee_profile_detail_exposes_cumulative_time_account(self):
        self.profile.contract_start_date = date(2026, 5, 1)
        self.profile.save()
        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 5, 15),
            start_time=time(9, 0),
            end_time=time(17, 0),
            entry_type=ENTRY_TYPE_ACTUAL,
        )
        resp = self.client.get(
            reverse("employee_profile_detail", kwargs={
                "user_id": self.employee.id,
                "profile_id": self.profile.id,
            }),
            {"year": 2026, "month": 7},
        )
        self.assertEqual(resp.status_code, 200)
        may_balance = round(8.0 - 173.92, 2)
        june_balance = round(0 - 173.92, 2)
        july_balance = round(0 - 173.92, 2)
        self.assertEqual(resp.context["balance"], july_balance)
        self.assertEqual(
            resp.context["cumulative_balance"],
            round(may_balance + june_balance + july_balance, 2),
        )
        self.assertContains(resp, "Monthly balance")
        self.assertContains(resp, "Time account")

    def test_employee_detail_month_cards_include_cumulative_time_account(self):
        self.profile.contract_start_date = date(2026, 5, 1)
        self.profile.save()
        TimeEntry.objects.create(
            profile=self.profile,
            date=date(2026, 5, 15),
            start_time=time(9, 0),
            end_time=time(17, 0),
            entry_type=ENTRY_TYPE_ACTUAL,
        )
        resp = self.client.get(reverse("employee_detail", kwargs={"user_id": self.employee.id}))
        self.assertEqual(resp.status_code, 200)
        months = resp.context["profile_data"][0]["months"]
        july = next(row for row in months if row["year"] == 2026 and row["month"] == 7)
        may_balance = round(8.0 - 173.92, 2)
        june_balance = round(0 - 173.92, 2)
        july_balance = round(0 - 173.92, 2)
        self.assertEqual(july["balance"], july_balance)
        self.assertEqual(
            july["cumulative_balance"],
            round(may_balance + june_balance + july_balance, 2),
        )
        self.assertContains(resp, "Time account")
