#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/var/www/novaplatform"
VENV_BIN="$APP_DIR/venv/bin"
PYTHON="$VENV_BIN/python"
PIP="$VENV_BIN/pip"

cd "$APP_DIR"

$PIP install -r requirements.txt
$PYTHON manage.py migrate --noinput
$PYTHON manage.py collectstatic --noinput
$PYTHON manage.py check --deploy
$PYTHON manage.py makemigrations --check --dry-run

sudo systemctl daemon-reload
sudo systemctl restart novaplatform
sudo systemctl restart nginx

echo "Release completed successfully."
