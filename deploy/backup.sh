#!/usr/bin/env bash
# Daily database backup: a compressed pg_dump kept on the server for 14 days
# and, if BACKUP_REMOTE is set in .env.prod, copied off the server with rclone
# (for example to Oracle Object Storage or Google Drive).
#
#   cd ~/mhtalk && bash deploy/backup.sh
#
# Run it every night with cron (crontab -e):
#   0 3 * * * cd ~/mhtalk && bash deploy/backup.sh >> ~/backups/backup.log 2>&1
#
# Restore a backup:
#   gunzip -c ~/backups/mhtalk-<date>.sql.gz | docker compose -f docker-compose.prod.yml \
#     --env-file .env.prod exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=".env.prod"
env_value() { grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '"' || true; }

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
REMOTE="${BACKUP_REMOTE:-$(env_value BACKUP_REMOTE)}"
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE")

mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/mhtalk-$(date +%F-%H%M).sql.gz"

# Credentials come from the db container's own environment.
"${COMPOSE[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" --no-owner "$POSTGRES_DB"' | gzip > "$FILE.part"
mv "$FILE.part" "$FILE"
echo "[backup $(date '+%F %T')] wrote $FILE ($(du -h "$FILE" | cut -f1))"

find "$BACKUP_DIR" -name 'mhtalk-*.sql.gz' -mtime +"$KEEP_DAYS" -delete

if [ -n "$REMOTE" ]; then
  if command -v rclone >/dev/null 2>&1; then
    rclone copy "$FILE" "$REMOTE"
    rclone delete --min-age "${KEEP_DAYS}d" "$REMOTE" || true
    echo "[backup] copied to $REMOTE"
  else
    echo "[backup] BACKUP_REMOTE is set but rclone is not installed (sudo apt install rclone)" >&2
    exit 1
  fi
fi
