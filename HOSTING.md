# Hosting-Guide für Trackable

Dieser Guide erklärt alle Schritte, die für das Hosting von Trackable auf einem VPS oder Mini PC mit Coolify/Docker Compose notwendig sind.

## Voraussetzungen

- Server mit Linux (Ubuntu 20.04+ empfohlen)
- Mindestens 2 GB RAM
- 20 GB Festplattenspeicher
- Docker und Docker Compose installiert
- Domain-Name (optional, aber empfohlen)
- SMTP-Zugangsdaten (für E-Mail-Funktionalität)

## Vorbereitung des Servers

### 1. System aktualisieren

```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Docker und Docker Compose installieren

```bash
# Docker installieren
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Docker Compose installieren
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Prüfen ob Installation erfolgreich war
docker --version
docker-compose --version
```

### 3. Firewall konfigurieren

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

## Projekt部署

### 1. Repository auf den Server kopieren

```bash
# Via Git (empfohlen)
git clone <deine-repo-url> /opt/trackable
cd /opt/trackable

# Oder via SCP
scp -r trackable/ user@server:/opt/trackable
```

### 2. Umgebungsvariablen konfigurieren

```bash
# .env Datei erstellen
cp .env.example .env

# .env Datei bearbeiten
nano .env
```

**Wichtige Konfigurationen in der .env:**

```env
# Sicherheit
SECRET_KEY=<starker-zufälliger-key-generieren-mit: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DEBUG=False
ALLOWED_HOSTS=deine-domain.com,www.deine-domain.com

# Datenbank
DATABASE_URL=sqlite:///data/db.sqlite3

# E-Mail (IONOS Beispiel)
EMAIL_HOST=smtp.ionos.de
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=deine-email@domain.com
EMAIL_HOST_PASSWORD=dein-email-passwort
DEFAULT_FROM_EMAIL=noreply@deine-domain.com

# Backup und Cron
BACKUP_SCHEDULE=weekly
BACKUP_FILENAME=db_backup.sqlite3
MONTHLY_EMAIL_TIME=23:59
```

### 3. Docker Compose starten

```bash
# Volume erstellen (wichtig für persistente Daten)
docker volume create trackable_db_data

# Prod-Compose starten
docker-compose -f docker-compose.prod.yaml up -d --build

# Status prüfen
docker-compose -f docker-compose.prod.yaml ps

# Logs prüfen
docker-compose -f docker-compose.prod.yaml logs -f
```

## SSL-Zertifikat mit Let's Encrypt (empfohlen)

### Option 1: Nginx Reverse Proxy

Eine fertige, produktionsreife Konfiguration liegt unter `nginx/trackable.conf` im Repository.  
Sie enthält TLS 1.2/1.3, HSTS, Security-Header, Gzip, Rate-Limiting und optimierte Proxy-Buffer.

```bash
# Nginx und Certbot installieren
sudo apt install nginx certbot python3-certbot-nginx -y

# Konfiguration kopieren und Domain eintragen (3× CHANGEME ersetzen)
sudo cp /opt/trackable/nginx/trackable.conf /etc/nginx/sites-available/trackable
sudo nano /etc/nginx/sites-available/trackable

# Aktivieren und testen
sudo ln -s /etc/nginx/sites-available/trackable /etc/nginx/sites-enabled/
sudo nginx -t

# SSL-Zertifikat ausstellen (füllt ssl_certificate-Zeilen automatisch aus)
sudo certbot --nginx -d deine-domain.com -d www.deine-domain.com

sudo systemctl reload nginx
```

### Option 2: Caddy (einfacher)

```bash
# Caddy installieren
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy -y

# Caddyfile erstellen
sudo nano /etc/caddy/Caddyfile
```

**Caddyfile:**

```
deine-domain.com www.deine-domain.com {
    reverse_proxy localhost:8000
    
    header {
        X-Frame-Options "SAMEORIGIN"
        X-Content-Type-Options "nosniff"
        X-XSS-Protection "1; mode=block"
    }
    
    file_server
}
```

```bash
# Caddy neu starten
sudo systemctl reload caddy
```

## Coolify-Deployment (empfohlen)

Coolify ist der empfohlene Weg, Trackable zu hosten. Traefik übernimmt SSL, Deployments und Rollbacks automatisch.

### 1. Coolify installieren

```bash
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

### 2. Trackable in Coolify hinzufügen

1. Coolify Dashboard öffnen
2. Neues Projekt → Neue Ressource → **Docker Compose**
3. Repository-URL eintragen (GitHub, GitLab, etc.)
4. Build-Konfiguration:
   - Compose-Datei: `docker-compose.prod.yaml`
   - **Port: `8000`** (Container-interner Port — nicht den Host-Port ändern)
5. Environment-Variablen aus der Tabelle unten in der Coolify-UI eintragen
6. Domain konfigurieren → Deployen

> **Hinweis:** Die `ports`-Zeile in `docker-compose.prod.yaml` ist für Coolify irrelevant. Traefik routet direkt über das interne Docker-Netzwerk (`coolify`) auf Port 8000.

### 3. Was Coolify automatisch übernimmt

- SSL-Zertifikate (via Traefik + Let's Encrypt)
- Deployment bei Git-Push
- Rollbacks
- Log-Monitoring
- Health-Checks

### 4. Ersten Superuser anlegen

Nach dem ersten Deployment im Coolify-Terminal oder per SSH:

```bash
docker exec -it trackable-app python manage.py createsuperuser
```

Danach unter `https://deine-domain.com/admin/` weitere Benutzer anlegen. Eine öffentliche Registrierung gibt es nicht.

## Wartung und Überwachung

### Logs prüfen

```bash
# App-Logs
docker-compose -f docker-compose.prod.yaml logs app -f

# Cron-Logs
docker-compose -f docker-compose.prod.yaml logs cron -f
```

### Container neu starten

```bash
# Alle Container neu starten
docker-compose -f docker-compose.prod.yaml restart

# Nur App neu starten
docker-compose -f docker-compose.prod.yaml restart app
```

### Datenbank-Backup manuell

```bash
# Ins App-Container einloggen
docker-compose -f docker-compose.prod.yaml exec app bash

# Backup erstellen
python manage.py backup_db
```

### Update der Anwendung

```bash
# Neue Version ziehen
git pull origin main

# Container neu bauen und starten
docker-compose -f docker-compose.prod.yaml up -d --build

# Alte Container bereinigen
docker-compose -f docker-compose.prod.yaml down
```

## Backup-Strategie

### Automatische Backups

Die App erstellt automatisch wöchentliche Backups der SQLite-Datenbank:
- Zeitpunkt: Jeden Sonntag um 02:00 Uhr
- Speicherort: `/app/data/backups/db_backup.sqlite3`
- Alte Backups werden überschrieben

### Externe Backups (empfohlen)

Für zusätzliche Sicherheit:

```bash
# Backup-Skript erstellen
nano /opt/backup-trackable.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/opt/backups/trackable"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Docker-Volume backuppen
docker run --rm -v trackable_db_data:/data -v $BACKUP_DIR:/backup alpine tar czf /backup/trackable_db_$DATE.tar.gz /data

# Backup auf externen Server kopieren (z.B. rsync)
# rsync -avz $BACKUP_DIR user@backup-server:/backups/trackable/

# Alte Backups lösken (letzten 30 Tage behalten)
find $BACKUP_DIR -name "trackable_db_*.tar.gz" -mtime +30 -delete
```

```bash
# Skript ausführbar machen
chmod +x /opt/backup-trackable.sh

# Cron-Job für tägliches Backup hinzufügen
crontab -e
```

```
0 3 * * * /opt/backup-trackable.sh
```

## Sicherheit

### Firewall-Regeln prüfen

```bash
sudo ufw status
```

### Docker-Sicherheit

```bash
# Nur HTTPS erlauben
sudo ufw allow 443/tcp
sudo ufw deny 80/tcp

# Docker-Container-Update-Check
sudo docker-compose -f docker-compose.prod.yaml pull
```

### Django-Sicherheit

- `DEBUG=False` in der `.env`
- Starker `SECRET_KEY`
- `ALLOWED_HOSTS` korrekt konfiguriert
- Regelmäßige Updates: `pip install --upgrade -r requirements.txt`

## Performance-Optimierung

### Gunicorn-Worker anpassen

In `docker-compose.prod.yaml`:

```yaml
command: >
  sh -c "python manage.py migrate && 
         gunicorn trackable.wsgi:application --bind 0.0.0.0:8000 --workers 4 --threads 2"
```

### Datenbank-Optimierung

```bash
# SQLite-VACUUM
docker-compose -f docker-compose.prod.yaml exec app sqlite3 /app/data/db.sqlite3 "VACUUM;"
```

## Fehlersuche

### Container starten nicht

```bash
# Logs prüfen
docker-compose -f docker-compose.prod.yaml logs

# Prüfen ob Ports belegt sind
sudo lsof -i :8000
```

### E-Mail-Funktionalität prüfen

```bash
# Test-E-Mail senden
docker-compose -f docker-compose.prod.yaml exec app python manage.py shell
```

```python
from django.core.mail import send_mail
send_mail('Test', 'Test-Inhalt', 'noreply@deine-domain.com', ['deine-email@domain.com'])
```

### PWA-Installation prüfen

1. Developer Tools im Browser öffnen
2. Application-Tab prüfen
3. Manifest prüfen: `/static/manifest.json`
4. Service Worker registrieren

## Monitoring

### System-Monitoring

```bash
# System-Ressourcen prüfen
htop
df -h
free -m
```

### Docker-Monitoring

```bash
# Container-Statistiken
docker stats

# Container-Logs
docker-compose -f docker-compose.prod.yaml logs --tail=100
```

### Uptime-Monitoring

Tools wie UptimeRobot, Pingdom oder ähnliche können für Uptime-Monitoring verwendet werden.

## Support

Bei Problemen:
1. Logs prüfen
2. Docker-Container-Status prüfen
3. Firewall-Regeln prüfen
4. SSL-Zertifikat prüfen
5. .env-Datei prüfen

## Next Steps nach Deployment

1. **Superuser erstellen**: `docker exec -it trackable-app python manage.py createsuperuser`
2. **Benutzer anlegen**: Unter `/admin/` Benutzerkonten für alle Nutzer erstellen (keine öffentliche Registrierung)
3. **Profil erstellen**: Erstes Arbeitsprofil anlegen
4. **Testen**: Zeit eintragen, Tabelle ansehen, PDF exportieren
5. **E-Mail testen**: Passwort-Reset und monatliche E-Mails prüfen
6. **Backup-Test**: Backup-Skript testen
7. **Monitoring einrichten**: Uptime-Monitoring und Alerts konfigurieren
8. **Zugangsdaten**: Passwörter und Zugangsdaten sicher aufbewahren