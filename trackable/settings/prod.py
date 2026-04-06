from .base import *

DEBUG = False

# WhiteNoise: komprimiert + cache-busting Dateinamen (z.B. app.abc123.js)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/app/data/db.sqlite3",
    }
}

# ── TLS / HSTS ──────────────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REDIRECT_EXEMPT = [r"^health/$"]  # Healthcheck darf plain HTTP bleiben

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

# ── ALLOWED_HOSTS: dynamische Konfiguration für Coolify und Compose ──────────
from urllib.parse import urlparse

_hosts = config("ALLOWED_HOSTS", default="").strip()
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(",") if h.strip()]

# Auto-add standalone Domain_NAME
_subdomain = config("SUBDOMAIN", default="").strip()
_domain = config("DOMAIN_NAME", default="").strip()
if _subdomain and _domain:
    _full_domain = f"{_subdomain}.{_domain}"
    if _full_domain not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_full_domain)

# Auto-add Coolify domains if present
coolify_domains = config("SERVICE_FQDN_APP_8000", default="").strip()
if coolify_domains:
    for url in coolify_domains.split(","):
        parsed = urlparse(url.strip())
        if parsed.hostname and parsed.hostname not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(parsed.hostname)

if not ALLOWED_HOSTS:
    raise RuntimeError(
        "ALLOWED_HOSTS muss in der .env gesetzt sein (z.B. meine-domain.com), oder via Coolify / Standalone ENV konfiguriert sein."
    )

CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS]
