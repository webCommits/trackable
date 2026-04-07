from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core import mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()


class UserRegistrationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse("register")

    def test_user_registration_creates_inactive_user(self):
        response = self.client.post(
            self.register_url,
            {
                "username": "testuser",
                "email": "test@example.com",
                "first_name": "Test",
                "last_name": "User",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="testuser")
        self.assertFalse(user.is_active)
        self.assertFalse(user.email_confirmed)

    def test_registration_sends_confirmation_email(self):
        self.client.post(
            self.register_url,
            {
                "username": "testuser",
                "email": "test@example.com",
                "first_name": "Test",
                "last_name": "User",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Confirm", mail.outbox[0].subject)

    def test_email_confirmation_activates_user(self):
        self.client.post(
            self.register_url,
            {
                "username": "testuser",
                "email": "test@example.com",
                "first_name": "Test",
                "last_name": "User",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )

        user = User.objects.get(username="testuser")
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        response = self.client.get(
            reverse("email_confirm", kwargs={"uidb64": uid, "token": token})
        )

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.email_confirmed)

    def test_password_mismatch(self):
        response = self.client.post(
            self.register_url,
            {
                "username": "testuser",
                "email": "test@example.com",
                "first_name": "Test",
                "last_name": "User",
                "password": "testpass123",
                "password_confirm": "differentpass",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="testuser").exists())


class LoginTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.login_url = reverse("login")

    def test_login_success(self):
        response = self.client.post(
            self.login_url,
            {
                "username": "testuser",
                "password": "testpass123",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

    def test_login_failure(self):
        response = self.client.post(
            self.login_url,
            {
                "username": "testuser",
                "password": "wrongpass",
            },
        )

        self.assertEqual(response.status_code, 200)

    def test_login_unconfirmed_user_shows_error(self):
        self.client.post(
            reverse("register"),
            {
                "username": "unconfirmed",
                "email": "unconfirmed@example.com",
                "first_name": "Unconfirmed",
                "last_name": "User",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )

        response = self.client.post(
            self.login_url,
            {
                "username": "unconfirmed",
                "password": "testpass123",
            },
        )

        self.assertEqual(response.status_code, 200)


class LogoutTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")

    def test_logout(self):
        response = self.client.post(reverse("logout"), follow=True)
        self.assertEqual(response.status_code, 200)


class PasswordResetTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.reset_url = reverse("password_reset_request")

    def test_password_reset_request(self):
        response = self.client.post(
            self.reset_url,
            {
                "email": "test@example.com",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Passwort zurücksetzen", mail.outbox[0].subject)


class AdminEmailTestTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )
        self.client.login(username="admin", password="adminpass123")

    def test_email_test_page_loads(self):
        response = self.client.get("/admin/email-test/")
        self.assertEqual(response.status_code, 200)

    def test_email_test_sends_email(self):
        response = self.client.post(
            "/admin/email-test/",
            {"recipient": "test@example.com"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["test@example.com"])

    def test_email_test_requires_recipient(self):
        response = self.client.post("/admin/email-test/", {"recipient": ""})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_test_requires_staff(self):
        user = User.objects.create_user(
            username="regular", email="regular@example.com", password="pass123"
        )
        self.client.login(username="regular", password="pass123")
        response = self.client.get("/admin/email-test/")
        self.assertEqual(response.status_code, 302)
