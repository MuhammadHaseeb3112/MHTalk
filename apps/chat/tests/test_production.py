"""Production plumbing: health probe, ICE servers, DATABASE_URL parsing, auth throttling."""

import base64
import hashlib
import hmac

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from config.settings.base import _database_from_url


class HealthTests(TestCase):
    def test_health_is_public_and_ok(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"], "ok")


class IceServerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="+923040000001", password="StrongPass123!")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_requires_login(self):
        self.assertEqual(APIClient().get("/api/calls/ice-servers/").status_code, 401)

    @override_settings(WHATSUP_TURN_URLS=[], WHATSUP_TURN_SECRET="", WHATSUP_TURN_USERNAME="")
    def test_stun_only_by_default(self):
        servers = self.client.get("/api/calls/ice-servers/").json()["ice_servers"]
        self.assertEqual(len(servers), 1)
        self.assertTrue(servers[0]["urls"][0].startswith("stun:"))

    @override_settings(WHATSUP_TURN_URLS=["turn:turn.example.com:3478"], WHATSUP_TURN_SECRET="s3cret")
    def test_short_lived_coturn_credentials(self):
        turn = self.client.get("/api/calls/ice-servers/").json()["ice_servers"][1]
        self.assertTrue(turn["username"].endswith(f":{self.user.id}"))
        expected = base64.b64encode(
            hmac.new(b"s3cret", turn["username"].encode(), hashlib.sha1).digest()
        ).decode()
        self.assertEqual(turn["credential"], expected)

    @override_settings(
        WHATSUP_TURN_URLS=["turn:relay.example.com:80"], WHATSUP_TURN_SECRET="",
        WHATSUP_TURN_USERNAME="u", WHATSUP_TURN_PASSWORD="p",
    )
    def test_static_provider_credentials(self):
        turn = self.client.get("/api/calls/ice-servers/").json()["ice_servers"][1]
        self.assertEqual((turn["username"], turn["credential"]), ("u", "p"))


class DatabaseUrlTests(TestCase):
    def test_parses_hosted_postgres_url(self):
        db = _database_from_url("postgresql://neon%40user:p%23ss@ep-x.neon.tech:6543/whatsup?sslmode=require")
        self.assertEqual(db["USER"], "neon@user")
        self.assertEqual(db["PASSWORD"], "p#ss")
        self.assertEqual(db["HOST"], "ep-x.neon.tech")
        self.assertEqual(db["PORT"], "6543")
        self.assertEqual(db["NAME"], "whatsup")
        self.assertEqual(db["OPTIONS"], {"sslmode": "require"})


class AuthThrottleTests(TestCase):
    def test_login_is_rate_limited(self):
        from unittest import mock

        from rest_framework.throttling import ScopedRateThrottle

        from apps.accounts.views import LoginAPIView

        cache.clear()
        with mock.patch.object(LoginAPIView, "throttle_classes", [ScopedRateThrottle]), mock.patch.object(
            ScopedRateThrottle, "THROTTLE_RATES", {"auth": "3/min"}
        ):
            client = APIClient()
            codes = [
                client.post("/api/accounts/login/", {"phone_number": "+923049999999", "password": "x"}).status_code
                for _ in range(4)
            ]
        self.assertEqual(codes[-1], 429)
        self.assertNotIn(429, codes[:3])
        self.assertEqual(LoginAPIView.throttle_scope, "auth")


class DatabaseUrlIgnoredTests(TestCase):
    def test_non_postgres_url_does_not_switch_database(self):
        import os
        import subprocess
        import sys

        code = (
            "import os; os.environ['DATABASE_URL']='sqlite:///db.sqlite3'; os.environ['SECRET_KEY']='x';"
            "os.environ['DB_PASSWORD']='x'; os.environ['DB_HOST']='db';"
            "import config.settings.base as b; print(b.DATABASES['default']['ENGINE'], b.DATABASES['default']['HOST'])"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=os.getcwd(), env={**os.environ, "DJANGO_SETTINGS_MODULE": ""})
        self.assertEqual(out.stdout.split(), ["django.db.backends.postgresql", "db"], out.stderr)
