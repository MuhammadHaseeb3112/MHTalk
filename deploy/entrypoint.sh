#!/bin/sh
# Start-up for the production backend container.
set -e

# Apply database changes once per deploy (safe to re-run).
python manage.py migrate --noinput

# Nobody is connected right after a deploy: clear stale "online" counters.
python manage.py reset_presence || true

# Several worker processes share the load; Redis (Channels layer) connects
# them, so a message sent through one worker reaches sockets on the others.
exec uvicorn config.asgi:application \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --proxy-headers \
    --forwarded-allow-ips "*" \
    --ws-ping-interval 20 \
    --ws-ping-timeout 20 \
    --timeout-graceful-shutdown 15 \
    --no-server-header
