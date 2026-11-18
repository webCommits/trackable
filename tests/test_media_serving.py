import importlib
import shutil
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings
from django.urls import clear_url_caches

import trackable.urls as trackable_urls


class ServeMediaUrlsTest(SimpleTestCase):
    """trackable.urls builds urlpatterns at import time based on DEBUG/SERVE_MEDIA,
    so these tests reload the module under overridden settings and restore it
    afterwards."""

    def setUp(self):
        self.media_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        (self.media_root / "logo.png").write_bytes(b"fake-png-bytes")
        # Registered in setUp (not inside the override_settings block below)
        # so it runs after the test method returns and override_settings has
        # already restored the real settings - otherwise trackable.urls would
        # stay built against the overridden DEBUG/SERVE_MEDIA/MEDIA_ROOT values
        # for the rest of the test run.
        self.addCleanup(self._reload_urlconf)

    def _reload_urlconf(self):
        importlib.reload(trackable_urls)
        clear_url_caches()

    def test_existing_media_file_served_in_production(self):
        with override_settings(
            DEBUG=False, SERVE_MEDIA=True, MEDIA_ROOT=str(self.media_root)
        ):
            self._reload_urlconf()
            response = self.client.get("/media/logo.png")
            self.assertEqual(response.status_code, 200)

    def test_missing_media_file_returns_404_in_production(self):
        with override_settings(
            DEBUG=False, SERVE_MEDIA=True, MEDIA_ROOT=str(self.media_root)
        ):
            self._reload_urlconf()
            response = self.client.get("/media/does-not-exist.png")
            self.assertEqual(response.status_code, 404)

    def test_path_traversal_does_not_escape_media_root(self):
        with override_settings(
            DEBUG=False, SERVE_MEDIA=True, MEDIA_ROOT=str(self.media_root)
        ):
            self._reload_urlconf()
            response = self.client.get("/media/../settings.py")
            # Django's static.serve() rejects paths that escape
            # document_root (via safe_join), surfacing as 400 or 404 -
            # never a 200 with file contents leaked.
            self.assertIn(response.status_code, (400, 404))

    def test_media_not_served_without_serve_media_in_production(self):
        with override_settings(
            DEBUG=False, SERVE_MEDIA=False, MEDIA_ROOT=str(self.media_root)
        ):
            self._reload_urlconf()
            response = self.client.get("/media/logo.png")
            self.assertEqual(response.status_code, 404)
