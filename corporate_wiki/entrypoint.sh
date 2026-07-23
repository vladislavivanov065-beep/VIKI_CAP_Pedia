#!/bin/sh
# Runs once per container start, before the app server. Every step here is
# idempotent, so restarting the container never breaks or duplicates
# anything: migrate no-ops once the schema is current, collectstatic
# overwrites with identical files, and create_initial_admin skips itself
# once a superuser already exists (see apps/accounts/management/commands/
# create_initial_admin.py).
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py create_initial_admin

exec "$@"
