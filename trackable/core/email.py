"""Email utilities that support SiteConfiguration-based overrides."""
from django.core.mail import send_mail as django_send_mail
from django.core.mail import get_connection


def get_effective_connection():
    """Return email connection using SiteConfiguration if host is set, else None.
    
    When SiteConfiguration.email_host is non-empty, those DB-stored settings
    override the Django settings defaults (env vars). Returns None when no
    DB config is set, which means Django uses its default connection from
    settings.
    """
    try:
        from trackable.core.models import SiteConfiguration
        sc = SiteConfiguration.get()
        if sc.email_host:
            return get_connection(
                host=sc.email_host,
                port=sc.email_port,
                username=sc.email_host_user,
                password=sc.email_host_password,
                use_tls=sc.email_use_tls,
            )
    except Exception:
        # Table might not exist yet (before migration)
        pass
    return None


def get_effective_from_email():
    """Return the From address to use for outgoing email.

    Uses SiteConfiguration.default_from_email when it is non-empty, else
    falls back to settings.DEFAULT_FROM_EMAIL (env var).
    """
    try:
        from trackable.core.models import SiteConfiguration
        sc = SiteConfiguration.get()
        default_from_email = sc.default_from_email.strip()
        if default_from_email:
            return default_from_email
    except Exception:
        # Table might not exist yet (before migration)
        pass
    from django.conf import settings
    return settings.DEFAULT_FROM_EMAIL


def send_mail(subject, message, from_email, recipient_list, **kwargs):
    """Send email using SiteConfiguration if configured, else Django settings.

    Accepts the same arguments as django.core.mail.send_mail.
    The connection parameter cannot be overridden via kwargs.
    """
    connection = get_effective_connection()
    if not from_email:
        from_email = get_effective_from_email()
    return django_send_mail(
        subject, message, from_email, recipient_list,
        connection=connection, **kwargs,
    )


def is_registration_disabled():
    """Check if registration is disabled.
    
    Returns True if DISABLE_REGISTRATION env var is True (override),
    or if SiteConfiguration.registration_enabled is False.
    """
    from django.conf import settings
    if settings.DISABLE_REGISTRATION:
        return True
    try:
        from trackable.core.models import SiteConfiguration
        return not SiteConfiguration.get().registration_enabled
    except Exception:
        # Table might not exist yet
        return False
