#!/usr/bin/env bash
# Daily database backup: a compressed pg_dump kept on the server for 14 days,
# plus a weekly archive of uploaded files (photos, videos, voice notes). Both
# are copied off the server when .env.prod has either:
#   BACKUP_UPLOAD_URL  an Oracle Object Storage "pre-authenticated request" URL
#                      with object-write access to a bucket (simplest: no
#                      keys or tools to install, uploaded with curl), or
#   BACKUP_REMOTE      an rclone remote, e.g. oci:mhtalk-backups.
# Uploaded-files archive: on Sundays, or any day with BACKUP_MEDIA_NOW=1.
#
#   cd ~/mhtalk && bash deploy/backup.sh
#
# Run it every night with cron (crontab -e):
#   0 3 * * * cd ~/mhtalk && bash deploy/backup.sh >> ~/backups/backup.log 2>&1
#
# Restore a backup:
#   gunzip -c ~/backups/mhtalk-<date>.sql.gz | docker compose -f docker-compose.prod.yml \
#     --env-file .env.prod exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
# Restore uploaded files:
#   docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T web \
#     tar xzf - -C /app/media < ~/backups/mhtalk-media-<date>.tar.gz
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=".env.prod"
env_value() { grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '"' || true; }

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
REMOTE="${BACKUP_REMOTE:-$(env_value BACKUP_REMOTE)}"
UPLOAD_URL="${BACKUP_UPLOAD_URL:-$(env_value BACKUP_UPLOAD_URL)}"
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE")

mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/mhtalk-$(date +%F-%H%M).sql.gz"

# Credentials come from the db container's own environment.
"${COMPOSE[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" --no-owner "$POSTGRES_DB"' | gzip > "$FILE.part"
mv "$FILE.part" "$FILE"
echo "[backup $(date '+%F %T')] wrote $FILE ($(du -h "$FILE" | cut -f1))"

find "$BACKUP_DIR" -name 'mhtalk-*.sql.gz' -mtime +"$KEEP_DAYS" -delete

FILES=("$FILE")
if [ "$(date +%u)" = "7" ] || [ "${BACKUP_MEDIA_NOW:-}" = "1" ]; then
  MEDIA="$BACKUP_DIR/mhtalk-media-$(date +%F).tar.gz"
  "${COMPOSE[@]}" exec -T web tar czf - -C /app/media . > "$MEDIA.part"
  mv "$MEDIA.part" "$MEDIA"
  echo "[backup $(date '+%F %T')] wrote $MEDIA ($(du -h "$MEDIA" | cut -f1))"
  # Keep the two newest file archives on the server.
  ls -1t "$BACKUP_DIR"/mhtalk-media-*.tar.gz 2>/dev/null | tail -n +3 | xargs -r rm -f
  FILES+=("$MEDIA")
fi

if [ -n "$UPLOAD_URL" ]; then
  for item in "${FILES[@]}"; do
    curl -fsS --retry 3 -T "$item" "${UPLOAD_URL%/}/$(basename "$item")"
    echo "[backup] uploaded $(basename "$item") to Object Storage"
  done
fi

if [ -n "$REMOTE" ]; then
  if command -v rclone >/dev/null 2>&1; then
    for item in "${FILES[@]}"; do rclone copy "$item" "$REMOTE"; done
    rclone delete --min-age "${KEEP_DAYS}d" --include 'mhtalk-*.sql.gz' "$REMOTE" || true
    echo "[backup] copied to $REMOTE"
  else
    echo "[backup] BACKUP_REMOTE is set but rclone is not installed (sudo apt install rclone)" >&2
    exit 1
  fi
fi
