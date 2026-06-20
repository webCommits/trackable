from .base import *
import os
import tempfile

# Use a separate database to avoid clobbering the dev database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
    }
}

# Allow testserver host used by Django's test client
ALLOWED_HOSTS = ["*"]

# Use locmem email backend so tests can assert on mail.outbox
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Store uploaded files in a writable temp directory during tests.
MEDIA_ROOT = os.path.join(tempfile.gettempdir(), "trackable_test_media")

# Speed up tests with faster password hasher
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable the SetupRedirectMiddleware so that unauthenticated requests
# during tests are not redirected to the setup wizard.
# Build MIDDLEWARE list from base, removing the unwanted middleware.
# Simply rebuild the list without the setup redirect middleware.
MIDDLEWARE = [m for m in MIDDLEWARE if m != "trackable.core.middleware.SetupRedirectMiddleware"]
