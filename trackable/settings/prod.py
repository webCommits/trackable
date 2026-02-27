from .base import *

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/app/data/db.sqlite3",
    }
}

# ── TLS / HSTS ──────────────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_HSTS_SECONDS = 31536000          # 1 Jahr
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ── Cookie security ──────────────────────────────────────────────────────────
SESSION_COOKIE_SECURE   = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SECURE   = True
CSRF_COOKIE_HTTPONLY = True             # CSRF cookie nicht per JS auslesbar
CSRF_COOKIE_SAMESITE = "Lax"

# ── HTTP Headers ─────────────────────────────────────────────────────────────
SECURE_BROWSER_XSS_FILTER   = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# ── SECRET_KEY: unsichere Dev-Keys blockieren ───────────────────────────────────
if SECRET_KEY.startswith("django-insecure-"):
    raise RuntimeError(
        "SECRET_KEY ist auf einen unsicheren Dev-Wert gesetzt. "
        "Bitte einen sicheren Schlüssel in .env setzen."
    )

# ── ALLOWED_HOSTS: kein "*"-Fallback in Produktion ───────────────────────────
_hosts = config("ALLOWED_HOSTS", default="").strip()
if not _hosts:
    raise RuntimeError(
        "ALLOWED_HOSTS muss in der .env gesetzt sein (z.B. meine-domain.com)."
    )
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(",") if h.strip()]
