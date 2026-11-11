
from pathlib import Path
from datetime import timedelta
from decouple import config


from urllib.parse import parse_qs, unquote, urlparse
import os


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!

SECRET_KEY = config("SECRET_KEY")
# SECURITY WARNING: don't run with debug turned on in production!

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost",
    cast=lambda v: [host.strip() for host in v.split(",")]
)

# Application definition

INSTALLED_APPS = [
    # Django Apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",

    "daphne",

    "django.contrib.staticfiles",

    # Third-party Apps
    "corsheaders",
    "channels",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",


    # Local Apps
    "apps.accounts.apps.AccountsConfig",
    "apps.chat",
    "apps.status",
    "apps.calls",
    "apps.notifications",

    "drf_spectacular",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Serves /static/ (admin, API docs) efficiently from the app itself.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

ASGI_APPLICATION = "config.asgi.application"


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

def _database_from_url(url):
    """postgres://user:pass@host:5432/name?sslmode=require -> Django dict."""
    parts = urlparse(url)
    options = {key: values[-1] for key, values in parse_qs(parts.query).items()}
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parts.path.lstrip("/")),
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "",
        "PORT": str(parts.port or 5432),
        "OPTIONS": options,
    }


# Hosted databases (Neon, Supabase, Render...) give one DATABASE_URL; the
# local Docker setup keeps using the separate DB_* variables. Only a
# PostgreSQL URL is honoured (older .env files carry an unused sqlite URL).
DATABASE_URL = config("DATABASE_URL", default="")
if DATABASE_URL.startswith(("postgres://", "postgresql://")):
    _default_db = _database_from_url(DATABASE_URL)
else:
    _default_db = {
        "ENGINE": config(
            "DB_ENGINE",
            default="django.db.backends.postgresql",
        ),
        "NAME": config("DB_NAME", default="mhtalk_db"),
        "USER": config("DB_USER", default="mhtalk_user"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default="db"),
        "PORT": config("DB_PORT", default="5432"),
    }
# Under ASGI every request/WebSocket handler may run on a different thread,
# and a "persistent" connection stays open per thread, so persistent
# connections pile up until PostgreSQL refuses new clients. Django therefore
# recommends CONN_MAX_AGE=0 for ASGI; production adds a real connection pool
# (DB_POOL_MAX_SIZE, see production.py) for fast, bounded connection reuse.
_default_db["CONN_MAX_AGE"] = config("DB_CONN_MAX_AGE", default=0, cast=int)
_default_db["CONN_HEALTH_CHECKS"] = True

DATABASES = {"default": _default_db}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

AUTH_USER_MODEL = "accounts.User"


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),

    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",

    # Abuse protection. Counters live in the shared cache (Redis), so limits
    # hold across every server process. Login/register get a tight scope.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("THROTTLE_ANON", default="120/min"),
        "user": config("THROTTLE_USER", default="2000/min"),
        "auth": config("THROTTLE_AUTH", default="20/min"),
        "link_preview": config("THROTTLE_LINK_PREVIEW", default="60/min"),
        # Group invite link preview/join (per user).
        "invite": config("THROTTLE_INVITE", default="30/min"),
    },
}


SPECTACULAR_SETTINGS = {
    "TITLE": "MHTalk Backend API",
    "DESCRIPTION": """
    Production-ready real-time messaging and calling backend built with Django,
    Django REST Framework, Django Channels, Redis and WebRTC signaling.
    """,
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "CONTACT": {
        "name": "Muhammad Haseeb",
        "email": "mhasseb3112@gmail.com",
    },
    "LICENSE": {
        "name": "MIT",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),

    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,

    "UPDATE_LAST_LOGIN": True,

    "ALGORITHM": "HS256",

    "SIGNING_KEY": SECRET_KEY,

    "AUTH_HEADER_TYPES": ("Bearer",),

    "AUTH_TOKEN_CLASSES": (
        "rest_framework_simplejwt.tokens.AccessToken",
    ),

    "TOKEN_BLACKLIST_ENABLED": True,
}



# One Redis serves three jobs: the Channels layer (real-time fan-out between
# all server processes), the cache and the rate-limit counters. A hosted Redis
# gives a single REDIS_URL (rediss:// = TLS); local Docker uses REDIS_HOST.
REDIS_URL = config(
    "REDIS_URL",
    default=f"redis://{config('REDIS_HOST', default='redis')}:{config('REDIS_PORT', default=6379, cast=int)}/0",
)

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
            # Drop undelivered frames quickly and allow bursts (group chats).
            "expiry": 30,
            "capacity": 500,
            "group_expiry": 86400,
        },
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "mhtalk",
        "TIMEOUT": 300,
    }
}

# Separate frontend domain (e.g. Cloudflare Pages / Vercel) -> list it here.
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:5173,http://127.0.0.1:5173",
    cast=lambda v: [origin.strip() for origin in v.split(",") if origin.strip()],
)
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="",
    cast=lambda v: [origin.strip() for origin in v.split(",") if origin.strip()],
)

# Voice/video calls. Public STUN always; TURN relays calls for users behind
# strict networks. Either a coturn shared secret (short-lived credentials are
# generated per user) or a fixed username/password from a TURN provider.
MHTALK_TURN_URLS = config(
    "TURN_URLS",
    default="",
    cast=lambda v: [url.strip() for url in v.split(",") if url.strip()],
)
MHTALK_TURN_SECRET = config("TURN_SECRET", default="")
MHTALK_TURN_USERNAME = config("TURN_USERNAME", default="")
MHTALK_TURN_PASSWORD = config("TURN_PASSWORD", default="")
MHTALK_TURN_TTL_SECONDS = config("TURN_TTL_SECONDS", default=86400, cast=int)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": config("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        # 4xx responses are normal client errors, not server problems.
        "django.request": {"level": "ERROR"},
        "daphne": {"level": "WARNING"},
    },
}


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(config("MEDIA_ROOT", default=str(BASE_DIR / "media")))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Optional: keep uploads in S3-compatible object storage (Cloudflare R2,
# Backblaze B2, AWS S3...) instead of the server disk. Needs
# ``pip install django-storages[s3]`` (listed in requirements/production.txt).
if config("USE_S3_MEDIA", default=False, cast=bool):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": config("S3_BUCKET"),
            "endpoint_url": config("S3_ENDPOINT_URL", default="") or None,
            "access_key": config("S3_ACCESS_KEY"),
            "secret_key": config("S3_SECRET_KEY"),
            "region_name": config("S3_REGION", default="auto"),
            "custom_domain": config("S3_PUBLIC_DOMAIN", default="") or None,
            "querystring_auth": config("S3_SIGNED_URLS", default=True, cast=bool),
            "file_overwrite": False,
        },
    }

# Serve /media/ from Django even with DEBUG off (only when no proxy/bucket does it).
MHTALK_SERVE_MEDIA = config("MHTALK_SERVE_MEDIA", default=False, cast=bool)

# Uploads above this size are streamed to a temp file instead of RAM.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# WhatsApp-style message rules (override in .env-driven settings if needed).
# A sender may edit a text message for this many minutes after sending it.
MHTALK_EDIT_WINDOW_MINUTES = config("MHTALK_EDIT_WINDOW_MINUTES", default=15, cast=int)
# "Delete for everyone" is allowed for this many hours after sending.
MHTALK_DELETE_FOR_EVERYONE_HOURS = config("MHTALK_DELETE_FOR_EVERYONE_HOURS", default=48, cast=int)
# Maximum number of chats a user may pin.
MHTALK_MAX_PINNED_CHATS = 3
# Pinned messages per chat (WhatsApp allows 3; pinning another replaces the oldest).
MHTALK_MAX_PINNED_MESSAGES = 3

# Largest photo / video / document a chat message may carry (Caddy allows 110 MB).
CHAT_MAX_UPLOAD_MB = config("CHAT_MAX_UPLOAD_MB", default=100, cast=int)

# MHTalk AI (assistant chat). Leave the key empty to turn it off.
# Providers: gemini (free key, default), groq (free key), openai, anthropic.
# View once media opens only on phones (desktop browsers allow screenshots).
VIEW_ONCE_PHONE_ONLY = config("VIEW_ONCE_PHONE_ONLY", default=True, cast=bool)

MHTALK_AI_PROVIDER = config("MHTALK_AI_PROVIDER", default="gemini")
MHTALK_AI_API_KEY = config("MHTALK_AI_API_KEY", default="")
MHTALK_AI_MODEL = config("MHTALK_AI_MODEL", default="")
MHTALK_AI_BASE_URL = config("MHTALK_AI_BASE_URL", default="")
# GIF tab in the emoji panel (free key: https://developers.giphy.com/dashboard/)
GIPHY_API_KEY = config("GIPHY_API_KEY", default="")


# Web Push (background notifications when no tab is open). Generate a key
# pair with `python manage.py generate_vapid_keys`. Leave empty to disable.
VAPID_PUBLIC_KEY = config("VAPID_PUBLIC_KEY", default="")
VAPID_PRIVATE_KEY = config("VAPID_PRIVATE_KEY", default="")
VAPID_SUBJECT = config("VAPID_SUBJECT", default="mailto:admin@example.com")
# Run push jobs synchronously (tests only).
MHTALK_PUSH_INLINE = False
