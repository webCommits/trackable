FROM python:3.11-slim

# uv für extrem schnelle Builds
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1

# Use timeouts + retries to avoid apt-get hanging (>5 min) and getting
# SIGKILL (exit code 137) from the Docker builder on slow connections.
RUN apt-get update -o Acquire::http::Timeout=30 -o Acquire::Retries=3 -o Acquire::http::Pipeline-Depth=0 \
    && apt-get install -y --no-install-recommends --no-install-suggests \
        gcc \
        gettext \
        cron \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv pip install --system -r pyproject.toml

COPY . .

# Create /app/media here too: a fresh named volume mounted over a directory
# that doesn't exist yet in the image is created by Docker as root, which
# would make uploads (org logos/favicons) fail with PermissionError once the
# chown below switches the app to running as appuser.
RUN mkdir -p /app/data/backups /app/media

# Compile translations into the image so every container has them. The app
# service also runs compilemessages on start, but the cron service (which
# sends the monthly report emails) doesn't, so without this its mails were
# always English.
RUN find /app/locale -name '*.po' -exec sh -c 'msgfmt -o "${1%.po}.mo" "$1"' _ {} \;

# Start script for the "cron" service: snapshots the container's environment
# into /etc/trackable-cron.env before starting cron, since Debian cron does
# not otherwise pass it to the jobs below (see scripts/cron-start.sh).
COPY scripts/cron-start.sh /usr/local/bin/trackable-cron-start
RUN chmod 0755 /usr/local/bin/trackable-cron-start

# Crontab zur Buildzeit als root einrichten
# Jobs source /etc/trackable-cron.env first (written by trackable-cron-start)
# so they run with the container's real settings module/secrets instead of
# manage.py's bare DJANGO_SETTINGS_MODULE=trackable.settings.dev default.
# send_monthly_emails runs daily and decides itself whether today (in
# settings.TIME_ZONE) is a send day. Containers run in UTC: 21:30 UTC is
# 22:30 CET / 23:30 CEST, i.e. still on the send day in Germany.
# Grouped in a subshell so a missing/failed source is captured in the log
# too, instead of silently vanishing into cron's (absent) mail delivery.
RUN echo '0 2 * * 0 root ( . /etc/trackable-cron.env && cd /app && /usr/local/bin/python manage.py backup_db ) >> /var/log/cron.log 2>&1' > /etc/cron.d/trackable \
    && echo '30 21 * * * root ( . /etc/trackable-cron.env && cd /app && /usr/local/bin/python manage.py send_monthly_emails ) >> /var/log/cron.log 2>&1' >> /etc/cron.d/trackable \
    && chmod 0644 /etc/cron.d/trackable \
    && touch /var/log/cron.log

# Non-root user für sicheren Container-Betrieb (nur app, nicht cron)
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app \
    && chmod 775 /app/data
USER appuser

EXPOSE 8000

CMD ["gunicorn", "trackable.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]