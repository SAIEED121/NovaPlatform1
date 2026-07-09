#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/var/www/novaplatform"
ENV_FILE="$APP_DIR/.env"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

BACKUP_DIR="${BACKUP_DIR:-/var/backups/novaplatform}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_MEDIA_ENABLED="${BACKUP_MEDIA_ENABLED:-True}"
TIMESTAMP="$(date +%F_%H%M%S)"

mkdir -p "$BACKUP_DIR/db" "$BACKUP_DIR/media"

DB_ENGINE="${DB_ENGINE:-sqlite}"
if [ "$DB_ENGINE" = "postgres" ] || [ "$DB_ENGINE" = "postgresql" ]; then
  : "${DB_NAME:?DB_NAME is required for PostgreSQL backup}"
  : "${DB_USER:?DB_USER is required for PostgreSQL backup}"
  : "${DB_HOST:=127.0.0.1}"
  : "${DB_PORT:=5432}"

  DB_BACKUP_FILE="$BACKUP_DIR/db/db_${TIMESTAMP}.dump"
  PGPASSWORD="${DB_PASSWORD:-}" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -F c \
    -f "$DB_BACKUP_FILE"
else
  DB_PATH="$APP_DIR/db.sqlite3"
  DB_BACKUP_FILE="$BACKUP_DIR/db/db_${TIMESTAMP}.sqlite3"
  cp "$DB_PATH" "$DB_BACKUP_FILE"
fi

if [ "$BACKUP_MEDIA_ENABLED" = "True" ] || [ "$BACKUP_MEDIA_ENABLED" = "true" ] || [ "$BACKUP_MEDIA_ENABLED" = "1" ]; then
  MEDIA_PATH="${DJANGO_MEDIA_ROOT:-$APP_DIR/media}"
  if [ -d "$MEDIA_PATH" ]; then
    tar -czf "$BACKUP_DIR/media/media_${TIMESTAMP}.tar.gz" -C "$MEDIA_PATH" .
  fi
fi

find "$BACKUP_DIR/db" -type f -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR/media" -type f -mtime +"$RETENTION_DAYS" -delete

echo "Backup completed: $TIMESTAMP"
