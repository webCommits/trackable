<div align="center">
  <img src="static/img/trackable-logo.png" alt="trackable." height="64" />
  <h1>trackable.</h1>
  <p><strong>Simple, self-hosted time tracking &mdash; as a PWA.</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Django-5.0-0C4B33?style=flat-square&logo=django&logoColor=white" />
    <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white" />
    <img src="https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white" />
    <img src="https://img.shields.io/badge/PWA-installable-5A0FC8?style=flat-square&logo=pwa&logoColor=white" />
    <img src="https://img.shields.io/badge/i18n-EN%20%7C%20DE-orange?style=flat-square" />
  </p>
</div>

---

## Screenshots

<div align="center">
  <img src="images/screenshot-desktop.png" alt="trackable. Desktop" width="700" />
  <br/><br/>
  <img src="images/screenshot-mobile.png" alt="trackable. Mobile" width="300" />
</div>

---

## Features

- **📱 PWA** — Installable on iOS, Android, and desktop directly from the browser
- **⏰ Time tracking** — Quickly log start time, end time, and breaks per day
- **🗂 Multiple profiles** — Separate tracking for different clients or jobs
- **📊 Monthly overview** — Automatic calculation of total hours and earnings
- **📄 PDF export** — Export monthly tables as landscape PDFs
- **📧 Monthly email reports** — Automated summary email on the last day of each month
- **🔐 Authentication** — Registration, login, and password reset included
- **💾 Automatic backups** — Weekly SQLite database backups
- **🌍 English & German** — Auto-detects browser language; English by default, German when device locale is `de`
- **🎨 Catppuccin design** — Clean, mobile-first dark theme

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 5.0, Gunicorn |
| Frontend | Django Templates, CSS3, Vanilla JS |
| Database | SQLite (persistent Docker volume) |
| PDF | ReportLab |
| Email | Django SMTP with html2text |
| Hosting | Docker, Docker Compose |
| PWA | Web App Manifest |

---

## Self-Hosting with Docker

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- A reverse proxy (Nginx, Caddy, Traefik) &mdash; **required in production**
- A domain name (for HTTPS)

### 1. Clone the repository

```bash
git clone https://github.com/yourname/trackable.git
cd trackable
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```env
# Generate a secure key:
# python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY=your-secret-key-here

DEBUG=False
ALLOWED_HOSTS=yourdomain.com

EMAIL_HOST=smtp.yourprovider.com
EMAIL_HOST_USER=you@yourdomain.com
EMAIL_HOST_PASSWORD=your-smtp-password
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

### 3. Start the container

```bash
docker-compose -f docker-compose.prod.yaml up -d --build
```

The app starts on `127.0.0.1:8000`. Point your reverse proxy at this address.

### 4. Reverse proxy (Nginx example)

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8000\;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

### 5. Create your account

Open `https://yourdomain.com/accounts/register/` to create the first user.

### Updating

```bash
git pull
docker-compose -f docker-compose.prod.yaml up -d --build
```

### Coolify

trackable. is fully compatible with [Coolify](https://coolify.io). Point it at this repository, set the compose file to `docker-compose.prod.yaml`, and configure the environment variables in the Coolify UI.

---

## Local Development

### With Docker (recommended)

```bash
make dev
```

App runs at `http://localhost:8000`. Useful Makefile commands:

| Command | Description |
|---|---|
| `make dev` | Start dev server with live reload |
| `make logs` | Follow container logs |
| `make shell` | Django shell inside container |
| `make migrate` | Run database migrations |
| `make test` | Run test suite |

### Without Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# set DEBUG=True in .env

python manage.py migrate
python manage.py compilemessages
python manage.py runserver
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | &mdash; | Django secret key (required) |
| `DEBUG` | `False` | Set `True` for development only |
| `ALLOWED_HOSTS` | &mdash; | Comma-separated list of allowed domains |
| `EMAIL_HOST` | `localhost` | SMTP host |
| `EMAIL_PORT` | `587` | SMTP port |
| `EMAIL_USE_TLS` | `True` | Use STARTTLS |
| `EMAIL_HOST_USER` | &mdash; | SMTP username |
| `EMAIL_HOST_PASSWORD` | &mdash; | SMTP password |
| `DEFAULT_FROM_EMAIL` | &mdash; | From address for outgoing mail |
| `BACKUP_SCHEDULE` | `weekly` | Backup frequency (`daily` / `weekly`) |
| `BACKUP_FILENAME` | `db_backup.sqlite3` | Backup file name |
| `MONTHLY_EMAIL_TIME` | `23:59` | Time to send monthly reports (HH:MM) |

---

## Internationalization

trackable. ships with **English** (default) and **German** translations.

Language is detected automatically from the `Accept-Language` header sent by the browser or device — no configuration needed. Set your OS or browser language to German and the interface switches automatically.

---

## License

[MIT](LICENSE) &copy; 2026 webCommits web Designs

---

<div align="center">
  <br/>
  <p>If trackable. saves you time, consider buying me a coffee ☕</p>
  <a href="https://paypal.me/dcmbrbeats">
    <img src="https://img.shields.io/badge/PayPal-Buy%20me%20a%20coffee-00457C?style=for-the-badge&logo=paypal&logoColor=white" alt="Buy me a coffee via PayPal" />
  </a>
  <br/><br/>
  <a href="https://www.webcommits.info">
    <img src="static/img/webcommits.png" alt="webCommits web Designs" height="32" />
  </a>
  <br/>
  <sub>Built with ❤ by <a href="https://www.webcommits.info">webCommits</a></sub>
</div>
