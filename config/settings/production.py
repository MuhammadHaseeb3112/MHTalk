"""
Production settings.

    DJANGO_SETTINGS_MODULE=config.settings.production

Everything secret or host-specific comes from environment variables
(see .env.example, section "Production"). Runs behind a TLS-terminating
reverse proxy (Caddy / Render / Koyeb...), which sets X-Forwarded-Proto.
"""

from .base import *  # noqa: F401,F403
from decouple import config

DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="",
    cast=lambda v: [host.strip() for host in v.split(",") if host.strip()],
)
# The container health check calls the app directly on 127.0.0.1.
ALLOWED_HOSTS += [host for host in ("127.0.0.1", "localhost") if host not in ALLOWED_HOSTS]

# The proxy terminates HTTPS; trust its header so Django knows the request
# was secure (absolute URLs, secure cookies, redirects).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)
SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

STATIC_ROOT = BASE_DIR / "staticfiles"

# PostgreSQL connection pool (psycopg_pool), one per server process. Total
# connections = WEB_CONCURRENCY x DB_POOL_MAX_SIZE; keep it below the
# database's limit (free hosted plans often allow 20-100).
DB_POOL_MAX_SIZE = config("DB_POOL_MAX_SIZE", default=10, cast=int)


def enable_db_pool(database):
    if DB_POOL_MAX_SIZE <= 0 or not database["ENGINE"].endswith("postgresql"):
        return
    database.setdefault("OPTIONS", {})["pool"] = {
        "min_size": 1,
        "max_size": DB_POOL_MAX_SIZE,
        "timeout": 15,  # seconds a request waits for a free connection
        "max_idle": 300,
    }
    database["CONN_MAX_AGE"] = 0  # the pool owns connection reuse
    database["CONN_HEALTH_CHECKS"] = False


enable_db_pool(DATABASES["default"])

# Several server processes share the database: presence counters are reset
# once per deploy by the entrypoint, not by every worker on start-up.
import os  # noqa: E402

os.environ.setdefault("MHTALK_RESET_PRESENCE_ON_STARTUP", "0")
