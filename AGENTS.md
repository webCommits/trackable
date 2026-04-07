# AGENTS.md

## Development

```bash
make dev          # Start dev server (Docker) at localhost:8000
make test         # Run Django test suite
make shell        # Django shell inside container
make migrate      # Run migrations
```

Dev container uses `trackable/settings/dev.py` with console email backend and SQLite at project root.

## Project Structure

Django 5.0 app with custom user model (`accounts.User`):

- `trackable/` — project root (settings, urls, wsgi)
- `trackable/accounts/` — custom User model, auth views, email confirmation
- `trackable/profiles/` — user profiles (client/job tracking)
- `trackable/timetracking/` — core time entry, vacation logic
- `trackable/core/` — shared models (Holiday), management commands
- `trackable/organizations/` — Organization & OrganizationMembership models, manager/employee roles, org dashboard
- `templates/` — Django templates
- `locale/de/` — German translations (`.po`/`.mo`)

## Key Conventions

- Custom user model: `AUTH_USER_MODEL = "accounts.User"` — use `get_user_model()` in tests
- Migrations required before running after model changes
- `compilemessages` required after changing `.po` translation files
- Tests use standard Django `TestCase` — run via `make test` or `python manage.py test`

## Production Notes

- Uses `trackable/settings/prod.py` (WhiteNoise for static files, Gunicorn)
- Requires `SECRET_KEY` and `ALLOWED_HOSTS` in `.env` — will crash with generic/missing values
- Production runs migrations + collectstatic + compilemessages on startup