#!/bin/sh
# Entrypoint for the "cron" container/service.
#
# Debian's cron does NOT pass the container's environment to the jobs it
# runs (/etc/environment is empty in this image), so management commands
# invoked from /etc/cron.d/trackable would otherwise run with manage.py's
# default DJANGO_SETTINGS_MODULE=trackable.settings.dev instead of the
# production settings/secrets actually configured for this container.
#
# This script snapshots the container's current environment (including
# secrets such as SECRET_KEY and SMTP credentials) into a root-only file
# that the cron jobs source before running, then starts cron.
#
# Usage:
#   trackable-cron-start             snapshot env, then exec cron -f -L ...
#   trackable-cron-start --env-only  snapshot env only, exit 0, don't start cron
#                                    (used by docker-entrypoint.sh, which starts
#                                    cron itself in the background)
#
# Must run as root (same requirement as cron itself).
#
# NOTE: relies on /bin/sh being dash (the default on this Debian-based
# image), because `export -p` on dash prints `export NAME='value'` lines
# that can be `. sourced` directly. bash's `export -p` instead prints
# `declare -x NAME="value"`, which the exclusion grep below and the sourcing
# in /etc/cron.d/trackable are not written to handle. Keep the shebang as
# `#!/bin/sh`, not `#!/bin/bash`.
set -eu

ENV_FILE=/etc/trackable-cron.env
TMP_FILE="${ENV_FILE}.tmp.$$"

fix_media_ownership() {
    # Self-heal pre-existing root-owned media volumes (created before /app/media
    # existed in the image, or by some other root-owned process) so the app
    # container, which runs as appuser, can write uploads to them again.
    # Top-level directory only - NOT recursive - to keep this cheap and safe
    # to run on every cron-container start.
    # Best-effort: under `set -eu` a failing chown would otherwise abort this
    # script and keep cron from ever starting, so don't let it fail the script.
    if [ -d /app/media ] && id appuser >/dev/null 2>&1; then
        chown appuser:appuser /app/media 2>/dev/null \
            || echo "trackable-cron-start: warning: could not chown /app/media" >&2
    fi
}

snapshot_env() {
    # Ensure the snapshot is never created world/group readable, even for
    # the brief moment before the explicit chmod below.
    umask 077

    # `export -p` prints every currently-exported variable as a properly
    # shell-quoted `export NAME='value'` line, which can be `. sourced`
    # later. Exclude a handful of volatile/shell-bookkeeping variables that
    # are either meaningless or wrong once re-sourced in a cron job's shell.
    export -p | grep -Ev '^export (HOME|PWD|OLDPWD|SHLVL|HOSTNAME|_)=' > "$TMP_FILE"

    chmod 0600 "$TMP_FILE"
    chown root:root "$TMP_FILE"
    mv "$TMP_FILE" "$ENV_FILE"
}

snapshot_env
fix_media_ownership

if [ "${1:-}" = "--env-only" ]; then
    exit 0
fi

exec cron -f -L /var/log/cron.log
