#!/bin/sh
set -e

# NOTE: this entrypoint is currently not referenced by the Dockerfile
# (no ENTRYPOINT/CMD uses it) nor by any docker-compose.*.yaml service
# (they all set their own `command:`), so it has no effect today. Kept
# in sync regardless in case it is wired up in the future.

# Start cron in the background (cron daemon needs root). Only root can run
# cron; if this entrypoint ends up running as a non-root user (e.g.
# "appuser", the Dockerfile's default USER), skip cron instead of failing,
# since that user could never start it anyway.
if [ "$(id -u)" = "0" ]; then
    # Snapshot the environment for cron jobs to source, using the same
    # atomic snapshot logic as the "cron" service's entrypoint — see
    # scripts/cron-start.sh for why this is necessary and the excluded vars.
    trackable-cron-start --env-only

    cron -f &
    CRON_PID=$!
else
    echo "docker-entrypoint.sh: not running as root, skipping cron startup" >&2
    CRON_PID=""
fi

# Cleanup on exit
trap '[ -n "$CRON_PID" ] && kill $CRON_PID 2>/dev/null; exit 0' INT TERM

# Run Django management commands, then gunicorn
python manage.py migrate \
    && python manage.py collectstatic --noinput \
    && python manage.py compilemessages \
    && exec gunicorn trackable.wsgi:application --bind 0.0.0.0:8000 --workers 3
