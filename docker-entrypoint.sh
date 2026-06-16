#!/bin/sh
set -e

# Start cron in the background (cron daemon needs root)
cron -f &
CRON_PID=$!

# Cleanup on exit
trap 'kill $CRON_PID 2>/dev/null; exit 0' INT TERM

# Run Django management commands, then gunicorn
python manage.py migrate \
    && python manage.py collectstatic --noinput \
    && python manage.py compilemessages \
    && exec gunicorn trackable.wsgi:application --bind 0.0.0.0:8000 --workers 3
