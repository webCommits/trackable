from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from trackable.core.models import SiteConfiguration

User = get_user_model()


class SetupStep2AuthTest(TestCase):
    """setup_step2 must only be reachable by an authenticated superuser.

    Note: the `test` settings disable SetupRedirectMiddleware, so hitting
    these URLs directly (without being redirected there first) exercises
    exactly the view-level auth checks under test.
    """

    def setUp(self):
        self.client = Client()
        self.url = reverse("setup_step2")
        self.superuser = User.objects.create_superuser(
            username="setupadmin", email="setupadmin@example.com", password="adminpass123"
        )

    def test_anonymous_get_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_anonymous_post_redirects_to_login_and_does_not_modify_config(self):
        config = SiteConfiguration.get()
        self.assertFalse(config.setup_completed)
        self.assertTrue(config.registration_enabled)

        response = self.client.post(
            self.url,
            {
                "email_host": "evil.example.com",
                "email_host_password": "stolen",
                "allowed_hosts": "evil.example.com",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

        config.refresh_from_db()
        self.assertFalse(config.setup_completed)
        self.assertEqual(config.email_host, "")
        self.assertEqual(config.email_host_password, "")
        self.assertEqual(config.allowed_hosts, "")

    def test_non_superuser_denied(self):
        User.objects.create_user(
            username="regular", email="regular@example.com", password="regularpass123"
        )
        self.client.login(username="regular", password="regularpass123")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_superuser_get_succeeds(self):
        self.client.login(username="setupadmin", password="adminpass123")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_superuser_post_completes_setup(self):
        self.client.login(username="setupadmin", password="adminpass123")

        response = self.client.post(self.url, {"registration_enabled": "on"})

        self.assertEqual(response.status_code, 302)
        config = SiteConfiguration.get()
        self.assertTrue(config.setup_completed)


class SetupStep1NoTokenTest(TestCase):
    """SETUP_TOKEN empty (default) -> behavior unchanged from before the fix."""

    def test_get_returns_200_without_token(self):
        response = self.client.get(reverse("setup_step1"))
        self.assertEqual(response.status_code, 200)

    def test_post_creates_superuser_without_token(self):
        response = self.client.post(
            reverse("setup_step1"),
            {
                "username": "setupadmin",
                "email": "setupadmin@example.com",
                "password": "setuppass123",
                "password_confirm": "setuppass123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            User.objects.filter(username="setupadmin", is_superuser=True).exists()
        )


@override_settings(SETUP_TOKEN="secret-token-123")
class SetupStep1TokenTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("setup_step1")

    def test_get_without_token_is_forbidden(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_get_with_wrong_token_is_forbidden(self):
        response = self.client.get(self.url, {"token": "wrong-token"})
        self.assertEqual(response.status_code, 403)

    def test_get_with_correct_token_returns_200(self):
        response = self.client.get(self.url, {"token": "secret-token-123"})
        self.assertEqual(response.status_code, 200)

    def test_post_without_token_is_forbidden_and_creates_no_user(self):
        response = self.client.post(
            self.url,
            {
                "username": "setupadmin",
                "email": "setupadmin@example.com",
                "password": "setuppass123",
                "password_confirm": "setuppass123",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="setupadmin").exists())

    def test_post_with_wrong_token_is_forbidden_and_creates_no_user(self):
        response = self.client.post(
            self.url,
            {
                "token": "wrong-token",
                "username": "setupadmin",
                "email": "setupadmin@example.com",
                "password": "setuppass123",
                "password_confirm": "setuppass123",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="setupadmin").exists())

    def test_post_with_correct_token_creates_superuser(self):
        response = self.client.post(
            self.url,
            {
                "token": "secret-token-123",
                "username": "setupadmin",
                "email": "setupadmin@example.com",
                "password": "setuppass123",
                "password_confirm": "setuppass123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            User.objects.filter(username="setupadmin", is_superuser=True).exists()
        )


@override_settings(SETUP_TOKEN="secret-token-123")
class SetupStep1TokenWithExistingAdminTest(TestCase):
    """When a superuser already exists, setup_step1 shows the "admin
    already exists" info page instead of the creation form — but that
    branch must still be behind the SETUP_TOKEN gate, not reachable (or
    even distinguishable from the 403 page) without it.
    """

    def setUp(self):
        self.client = Client()
        self.url = reverse("setup_step1")
        User.objects.create_superuser(
            username="existingadmin",
            email="existingadmin@example.com",
            password="adminpass123",
        )

    def test_get_without_token_returns_403_not_admin_exists_page(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "core/setup/token_required.html")
        self.assertTemplateNotUsed(response, "core/setup/admin_exists.html")

    def test_get_with_correct_token_returns_admin_exists_page(self):
        response = self.client.get(self.url, {"token": "secret-token-123"})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/setup/admin_exists.html")
