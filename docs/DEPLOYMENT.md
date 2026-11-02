# Deployment & scaling

This guide covers how MHTalk is built to serve many users, and three ways to
put it online for free or close to free.

## 1. Architecture

```
            browser (React SPA)
                 │  HTTPS + WSS
          ┌──────▼──────┐
          │    Caddy    │  TLS (Let's Encrypt), gzip/zstd, SPA files,
          │             │  /media (Range requests), reverse proxy
          └──┬───────┬──┘
     /api /ws│       │/media
   /admin    │       │
  ┌──────────▼───┐   └──► media volume / S3-compatible bucket
  │  uvicorn × N │  Django + DRF + Channels (one process per CPU core)
  └──┬────────┬──┘
     │        │ channel layer, cache, rate limits
     │   ┌────▼────┐
     │   │  Redis  │  fan-out between processes: a message sent through
     │   └─────────┘  worker 1 reaches sockets held by worker 3
  ┌──▼─────────┐
  │ PostgreSQL │  source of truth (psycopg connection pool per process)
  └────────────┘
  coturn (optional) – relays calls for users behind strict NAT
```

### What makes it hold up with many users

| Concern | What the code does |
|---|---|
| N+1 queries | `with_message_relations()` loads sender/profile, reply, forward, voice note, attachments and reactions for any number of messages in a fixed number of queries. `apps/chat/tests/test_query_counts.py` fails if any list endpoint's query count grows with data. |
| Read receipts in big groups | `persist_receipts_bulk()` marks hundreds of messages delivered/read with ~7 queries total (it used to be one pass per message, each looping over every group member). |
| Database connections | Django + ASGI leaks "persistent" connections per thread. Production uses a bounded `psycopg_pool` per process (`DB_POOL_MAX_SIZE`, default 10). Total connections = `WEB_CONCURRENCY × DB_POOL_MAX_SIZE`. |
| Many server processes | `uvicorn --workers $WEB_CONCURRENCY`. Redis (Channels layer) connects them; presence counters live in PostgreSQL and are reset once per deploy by the entrypoint. |
| Shared cache / rate limits | Redis cache: the same counters apply on every process. Login/register limited to `THROTTLE_AUTH` (20/min per IP); others `THROTTLE_ANON`/`THROTTLE_USER`. |
| Big histories | Messages are paged (`?limit=50&before=<id>`); indexes on `(room, created_at)`, receipts `(recipient, read_at)`, unique pairs for receipts/stars/reactions. |
| Large uploads | Streamed to disk above 5 MB (not held in RAM); served by Caddy or object storage, never through Python in production. |
| Calls | ICE servers come from `/api/calls/ice-servers/`; with coturn the server mints short-lived TURN credentials, so no TURN password ships in the JavaScript. |
| Health | `GET /api/health/` checks the database and Redis (used by Docker, Render and uptime monitors). |

Measured locally (2 vCPU, PostgreSQL 16, Redis 7, 2 uvicorn workers):
400 simultaneous WebSocket connections opened in under 3 s. 2,000 chat-list
requests (50 concurrent) completed with 0 errors and database connections
capped at 20. A message reached all 200 of the recipient's open tabs within
120 ms. Throughput is CPU-bound (~30 ms per chat-list request), so it
scales with cores: set `WEB_CONCURRENCY` to about 2 × cores.

### Beyond one server

1. Move PostgreSQL and Redis to managed services, and media to a bucket (`USE_S3_MEDIA`).
2. Run several identical app servers behind a load balancer. WebSockets need no sticky sessions, because Redis carries every event.
3. Add a PostgreSQL read replica for search/history if reads dominate.
4. For very large groups, swap `channels_redis` for `RedisPubSubChannelLayer` or a Redis Cluster.

## 2. Option A: one free VM (recommended, always on)

**Oracle Cloud Always Free.** An Arm (Ampere A1) VM runs the whole stack with
Docker. Sign-up asks for a card for verification. Oracle says it is not
charged on the free tier.

1. Create an Ubuntu VM (Ampere A1, 2 OCPU / 12 GB is plenty). Open ports 80 and 443, plus UDP 3478 and 49160–49200 for calls, in the VCN security list and in `ufw`/`iptables`.
2. Get a free domain, for example `yourname.duckdns.org`, pointing at the VM's public IP.
3. On the VM:
   ```bash
   curl -fsSL https://get.docker.com | sh
   git clone https://github.com/<you>/MHTalk.git && cd MHTalk
   cp deploy/env.prod.example .env.prod   # edit every "change-me"
   docker compose -f docker-compose.prod.yml --env-file .env.prod --profile turn up -d --build
   docker compose -f docker-compose.prod.yml --env-file .env.prod exec web python manage.py createsuperuser
   ```
4. Open `https://yourname.duckdns.org`. Caddy obtains the HTTPS certificate automatically.

Updating later: `git pull` and then the same `up -d --build` command. Migrations run automatically.

Backups: `docker compose -f docker-compose.prod.yml exec db pg_dump -U mhtalk mhtalk > backup.sql`
(keep it off GitHub — `*.sql` is git-ignored).

## 3. Option B: free PaaS pieces (no server to manage)

| Piece | Free service | Notes |
|---|---|---|
| Backend | Render web service (`render.yaml`) | No card. Sleeps after 15 min idle (about 1 min to wake), so incoming calls can't ring a sleeping server. |
| PostgreSQL | Neon | 0.5–1 GB, scales to zero, data kept. Do **not** use Render's free Postgres, which expires after 30 days. |
| Redis | Redis Cloud free (30 MB) | Works with Channels. Upstash's command quota is used up by Channels' constant polling. |
| Media | Cloudflare R2 / Backblaze B2 via `USE_S3_MEDIA` | The Render disk is wiped on every deploy. |
| Frontend | Render static site, Cloudflare Pages or Vercel | Set `VITE_API_URL=https://<api>/api/` and `VITE_WS_URL=wss://<api>`. |
| TURN | Cloudflare Realtime TURN or Metered | Set `TURN_URLS`, `TURN_USERNAME`, `TURN_PASSWORD`. |

Backend environment: `SECRET_KEY`, `DATABASE_URL` (Neon, `?sslmode=require`),
`REDIS_URL` (`rediss://...`), `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` and
`CSRF_TRUSTED_ORIGINS` (frontend URL), `WEB_CONCURRENCY=1`, `DB_POOL_MAX_SIZE=5`.

## 4. Option C: AWS

AWS's free plan for new accounts is credit-based (up to $200), and the account
closes after 6 months unless you upgrade. That is good for a trial or a demo,
not for a long-running free app. The same `docker-compose.prod.yml` runs on an
EC2 instance; the managed equivalents are RDS (PostgreSQL), ElastiCache
(Redis), S3 (media) and an ALB, all paid after the credits.

## 5. Checklist before going live

- [ ] `DEBUG=False`, a long random `SECRET_KEY`, real `ALLOWED_HOSTS`.
- [ ] `.env`, `.env.prod`, `sqlite_backup.json`, `*.sql` are **not** in Git (all ignored).
- [ ] `python manage.py check --deploy` shows no security errors.
- [ ] `/api/health/` returns `{"status": "ok"}`.
- [ ] A voice call works between two phones on mobile data (TURN works).
- [ ] Database backups are scheduled.
