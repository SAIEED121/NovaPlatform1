# NovaPlatform Production Deployment

## 1. Environment Variables
Create a `.env` file in `/var/www/novaplatform` based on `.env.example`.

Required minimum:
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- Database variables when using PostgreSQL (`DB_*`)
- `DB_SSLMODE` for managed PostgreSQL (recommended `require`)

Recommended production variables:
- `DJANGO_CSRF_COOKIE_HTTPONLY` (default `False`, set to `True` only if your frontend does not read CSRF cookie)
- `BACKUP_DIR`
- `BACKUP_RETENTION_DAYS`
- `BACKUP_MEDIA_ENABLED`

## 2. Dependencies
```bash
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Static Collection
```bash
python manage.py collectstatic --noinput
```
Static files will be written to `/var/www/novaplatform/staticfiles` (or `STATIC_ROOT`).

WhiteNoise is enabled for Django-level static serving (useful on platforms without Nginx).

## 4. Media
- User uploads are stored under `DJANGO_MEDIA_ROOT`.
- Nginx serves `/media/` directly from that folder.
- Ensure folder exists and is writable by `www-data`:
```bash
sudo mkdir -p /var/www/novaplatform/media
sudo chown -R www-data:www-data /var/www/novaplatform/media
```

## 5. Logging
- Application logs are written to `DJANGO_LOG_DIR/django.log` with daily rotation.
- Gunicorn logs:
  - `/var/www/novaplatform/logs/gunicorn-access.log`
  - `/var/www/novaplatform/logs/gunicorn-error.log`

Create and permission logs directory:
```bash
sudo mkdir -p /var/www/novaplatform/logs
sudo chown -R www-data:www-data /var/www/novaplatform/logs
```

## 6. Gunicorn
1. Copy service file:
```bash
sudo cp deploy/systemd/novaplatform.service /etc/systemd/system/novaplatform.service
```
2. Enable + start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable novaplatform
sudo systemctl start novaplatform
sudo systemctl status novaplatform
```

## 7. Nginx
1. Copy Nginx config:
```bash
sudo cp deploy/nginx/novaplatform.conf /etc/nginx/sites-available/novaplatform
sudo ln -s /etc/nginx/sites-available/novaplatform /etc/nginx/sites-enabled/novaplatform
```
2. Test and reload:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 8. Optional SSL (recommended)
Use Certbot after DNS points to your server:
```bash
sudo certbot --nginx -d example.com -d www.example.com
```

## 9. Health Endpoint
- Application health endpoint: `/healthz/`
- Nginx is configured to proxy `/healthz` to Gunicorn.
- Quick check:
```bash
curl -f https://example.com/healthz
```

Expected JSON response:
```json
{"status": "ok"}
```

## 10. One-command Release (optional)
```bash
bash deploy/scripts/release.sh
```

## 11. Backup Recommendations
Minimum backup policy:
- Database backup at least daily (retain 7-30 days).
- Media folder backup at least daily.
- Keep encrypted off-server backups (object storage or remote host).
- Test restore monthly on a staging environment.

Built-in backup automation in this repository:
- Script: `deploy/scripts/backup.sh`
- systemd service: `deploy/systemd/novaplatform-backup.service`
- systemd timer: `deploy/systemd/novaplatform-backup.timer`

Enable scheduled backups:
```bash
sudo cp deploy/systemd/novaplatform-backup.service /etc/systemd/system/novaplatform-backup.service
sudo cp deploy/systemd/novaplatform-backup.timer /etc/systemd/system/novaplatform-backup.timer
sudo chmod +x deploy/scripts/backup.sh
sudo systemctl daemon-reload
sudo systemctl enable --now novaplatform-backup.timer
sudo systemctl list-timers | grep novaplatform-backup
```

Run a manual backup test:
```bash
sudo systemctl start novaplatform-backup.service
sudo journalctl -u novaplatform-backup.service -n 50 --no-pager
```

Example PostgreSQL backup command:
```bash
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -F c -f /var/backups/novaplatform/db_$(date +%F).dump
```

Example media backup command:
```bash
rsync -a --delete /var/www/novaplatform/media/ /var/backups/novaplatform/media/
```

## 12. Deployment Checklist
- [ ] `DJANGO_DEBUG=False`
- [ ] Strong `DJANGO_SECRET_KEY` set in `.env`
- [ ] Correct `DJANGO_ALLOWED_HOSTS`
- [ ] `DJANGO_CSRF_TRUSTED_ORIGINS` uses `https://...`
- [ ] `DJANGO_USE_X_FORWARDED_HOST=True` when behind Nginx/Proxy
- [ ] Cookies are secure + SameSite configured (`DJANGO_*_COOKIE_SECURE`, `DJANGO_*_COOKIE_SAMESITE`)
- [ ] `DJANGO_SECURE_HSTS_SECONDS` and preload/subdomains configured for HTTPS-only production
- [ ] PostgreSQL configured (if used)
- [ ] `DB_SSLMODE=require` for managed PostgreSQL services
- [ ] `python manage.py migrate --noinput` completed
- [ ] `python manage.py collectstatic --noinput` completed
- [ ] `python manage.py check --deploy` passes without critical warnings
- [ ] Gunicorn service is active
- [ ] Nginx config test passes (`nginx -t`)
- [ ] Static and media URLs served correctly
- [ ] HTTPS enabled and valid certificate installed
- [ ] `https://example.com/healthz` returns `{"status": "ok"}`
- [ ] Database backup cron configured and restore tested
- [ ] Media backup job configured and restore tested
- [ ] `novaplatform-backup.timer` is enabled and active
