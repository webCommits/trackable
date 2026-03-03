FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    gettext \
    cron \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data/backups

# Crontab zur Buildzeit als root einrichten
RUN echo '0 2 * * 0 root cd /app && python manage.py backup_db >> /var/log/cron.log 2>&1' > /etc/cron.d/trackable \
    && echo '59 23 * * * root [ "$(date +\%d -d tomorrow)" = "01" ] && cd /app && python manage.py send_monthly_emails >> /var/log/cron.log 2>&1' >> /etc/cron.d/trackable \
    && chmod 0644 /etc/cron.d/trackable \
    && touch /var/log/cron.log

# Non-root user für sicheren Container-Betrieb (nur app, nicht cron)
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app \
    && chmod 775 /app/data
USER appuser

EXPOSE 8000

CMD ["gunicorn", "trackable.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]