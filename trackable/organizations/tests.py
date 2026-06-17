from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

from trackable.organizations.forms import EmployeeCreateForm
from trackable.organizations.models import Organization, OrganizationMembership


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
