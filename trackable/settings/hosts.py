"""Pure helper for parsing FQDN lists (e.g. Coolify's SERVICE_FQDN_APP_8000)
into plain hostnames.

This module must NOT import Django or any Django settings module, so it can
be unit-tested in isolation without triggering side effects such as
``trackable.settings.prod``'s ``ALLOWED_HOSTS`` validation (which raises if
``ALLOWED_HOSTS`` ends up empty).
"""
from urllib.parse import urlparse


def hosts_from_fqdn_list(value: str) -> list[str]:
    """Parse a comma-separated list of FQDNs into lowercase hostnames.

    Each entry may or may not include a scheme (``https://``), a port
    (``:8000``), and/or a path. Coolify has provided this value both with a
    scheme (older versions, e.g. "https://app.example.com") and without one
    (v4.6+, e.g. "app.example.com:8000"), and it may contain multiple
    comma-separated domains. Empty or unparsable entries are skipped.
    """
    hosts: list[str] = []
    if not value:
        return hosts

    for entry in value.split(","):
        entry = entry.strip()
        if not entry:
            continue

        # urlparse() only populates .hostname when a scheme/netloc is
        # present. Without a scheme, "host:port" is parsed as path, not
        # netloc — so add a scheme-less "//" prefix to force netloc parsing
        # when the entry doesn't already look like it has a scheme.
        candidate = entry if "//" in entry else f"//{entry}"
        hostname = urlparse(candidate).hostname
        if hostname:
            hosts.append(hostname.lower())

    return hosts
