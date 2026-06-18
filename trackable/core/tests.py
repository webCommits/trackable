from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation


class SetLanguageViewTest(TestCase):
    def test_set_language_sets_cookie_for_german(self):
        response = self.client.post(
            reverse("set_language"), {"language": "de"}, follow=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "de")

    def test_set_language_sets_cookie_for_english(self):
        response = self.client.post(
            reverse("set_language"), {"language": "en"}, follow=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "en")

    def test_set_language_ignores_invalid_language(self):
        response = self.client.post(
            reverse("set_language"), {"language": "fr"}, follow=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, response.cookies)

    def test_set_language_redirects_to_referer(self):
        response = self.client.post(
            reverse("set_language"),
            {"language": "de"},
            HTTP_REFERER="/app/",
            follow=False,
        )
        self.assertEqual(response.url, "/app/")

    def test_set_language_defaults_to_home_without_referer(self):
        response = self.client.post(
            reverse("set_language"), {"language": "en"}, follow=False
        )
        self.assertEqual(response.url, "/")

    def test_url_reverse(self):
        self.assertEqual(reverse("set_language"), "/set-language/")


class TranslationCoverageTest(TestCase):
    def test_employee_at_org_is_translated(self):
        translation.activate("de")
        self.addCleanup(translation.deactivate)
        result = translation.gettext("Employee at %(org)s") % {"org": "Acme"}
        self.assertEqual(result, "Mitarbeiter bei Acme")

    def test_employee_role_is_translated(self):
        translation.activate("de")
        self.addCleanup(translation.deactivate)
        self.assertEqual(translation.gettext("Employee"), "Mitarbeiter")
