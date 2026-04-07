from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.core.models import Holiday
from trackable.profiles.models import Profile
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
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="newemp")
        self.assertTrue(user.email_confirmed)
        membership = OrganizationMembership.objects.get(user=user)
        self.assertEqual(membership.role, "employee")
        self.assertEqual(membership.organization, self.org)

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
        response = self.client.post(
            reverse("employee_remove", kwargs={"user_id": employee.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(OrganizationMembership.objects.filter(user=employee).exists())
        self.assertTrue(User.objects.filter(username="employee").exists())

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
