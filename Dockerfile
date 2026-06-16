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
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv pip install --system -r pyproject.toml

COPY . .

RUN mkdir -p /app/data/backups

# Crontab zur Buildzeit als root einrichten
RUN echo '0 2 * * 0 root cd /app && python manage.py backup_db >> /var/log/cron.log 2>&1' > /etc/cron.d/trackable \
    && echo '59 23 * * * root [ "$(date +\%d -d tomorrow)" = "01" ] && cd /app && python manage.py send_monthly_emails >> /var/log/cron.log 2>&1' >> /etc/cron.d/trackable \
    && chmod 0644 /etc/cron.d/trackable \
    && touch /var/log/cron.log

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

CMD ["gunicorn", "trackable.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
