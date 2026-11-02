"""
MHTalk AI: an assistant chat built into the app (like the AI chat in
WhatsApp, under our own name).

The browser sends the recent conversation; the server adds the API key and
forwards it to the AI provider, so the key never reaches the browser.
Configure it in ``.env`` (free options first):

    # Google Gemini - free key from https://aistudio.google.com/apikey
    WHATSUP_AI_PROVIDER=gemini
    WHATSUP_AI_API_KEY=AIza...

    # Groq - free key from https://console.groq.com/keys
    WHATSUP_AI_PROVIDER=groq
    WHATSUP_AI_API_KEY=gsk_...

    # Also supported: openai (or any OpenAI-compatible service via
    # WHATSUP_AI_BASE_URL) and anthropic.
    WHATSUP_AI_MODEL=...   # optional, a sensible default per provider

Only the Python standard library is used, so no new package is needed.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# OpenAI-compatible chat-completions endpoints (Gemini and Groq both offer one).
PROVIDERS = {
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-3.5-flash-lite",
        "label": "Google Gemini",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "label": "Groq",
    },
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
        "label": "OpenAI",
    },
    "anthropic": {"url": ANTHROPIC_URL, "model": "claude-haiku-5-5", "label": "Anthropic"},
}
MAX_TURNS = 30
MAX_CHARS = 4000
PER_MINUTE = 20

SYSTEM_PROMPT = (
    "You are MHTalk AI, a friendly assistant inside the MHTalk messenger. "
    "Answer briefly and clearly, like a helpful chat message. Use short "
    "paragraphs or simple '-' bullet lists, and reply in the user's language "
    "(including Roman Urdu when the user writes in it)."
)


def ai_settings():
    provider = (getattr(settings, "WHATSUP_AI_PROVIDER", "") or "gemini").strip().lower()
    if provider not in PROVIDERS:
        provider = "gemini"
    preset = PROVIDERS[provider]
    base_url = (getattr(settings, "WHATSUP_AI_BASE_URL", "") or "").strip().rstrip("/")
    url = preset["url"]
    if base_url and provider != "anthropic":
        url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    return {
        "provider": provider,
        "label": preset["label"],
        "url": url,
        "key": (getattr(settings, "WHATSUP_AI_API_KEY", "") or "").strip(),
        "model": (getattr(settings, "WHATSUP_AI_MODEL", "") or "").strip() or preset["model"],
    }


def _post_json(url, body, headers, timeout):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"content-type": "application/json", **headers},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (configured https URL)
        return json.loads(response.read().decode("utf-8"))


def call_model(messages, config, timeout=60):
    """Send the conversation to the configured provider and return the reply text."""
    if config["provider"] == "anthropic":
        payload = _post_json(
            config["url"],
            {"model": config["model"], "max_tokens": 1024, "system": SYSTEM_PROMPT, "messages": messages},
            {"x-api-key": config["key"], "anthropic-version": "2023-06-01"},
            timeout,
        )
        parts = [block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"]
        return "".join(parts).strip()

    payload = _post_json(
        config["url"],
        {
            "model": config["model"],
            "max_tokens": 1024,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        },
        {"authorization": f"Bearer {config['key']}"},
        timeout,
    )
    choices = payload.get("choices") or []
    if not choices:
        return ""
    content = (choices[0].get("message") or {}).get("content") or ""
    if isinstance(content, list):  # some providers return content parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content).strip()


def clean_messages(raw):
    """Validate the client's history: alternating user/assistant text, user last."""
    if not isinstance(raw, list) or not raw:
        return None
    messages = []
    for item in raw[-MAX_TURNS:]:
        if not isinstance(item, dict):
            return None
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            return None
        content = content.strip()[:MAX_CHARS]
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n\n" + content
        else:
            messages.append({"role": role, "content": content})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    if not messages or messages[-1]["role"] != "user":
        return None
    return messages


class AssistantAPIView(APIView):
    """GET: is the assistant set up?  POST: send the chat, get a reply."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="MHTalk AI status", tags=["Assistant"])
    def get(self, request):
        config = ai_settings()
        return Response(
            {
                "enabled": bool(config["key"]),
                "name": "MHTalk AI",
                "provider": config["provider"],
                "provider_label": config["label"],
                "model": config["model"],
            }
        )

    @extend_schema(summary="Chat with MHTalk AI", tags=["Assistant"])
    def post(self, request):
        config = ai_settings()
        if not config["key"]:
            return Response(
                {"detail": "MHTalk AI isn't set up yet. Add a free Gemini key as WHATSUP_AI_API_KEY in the backend .env file and restart."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        messages = clean_messages(request.data.get("messages"))
        if messages is None:
            return Response({"detail": "Send at least one message."}, status=status.HTTP_400_BAD_REQUEST)

        key = f"whatsup-ai-rate:{request.user.pk}"
        count = cache.get(key, 0)
        if count >= PER_MINUTE:
            return Response({"detail": "You're sending messages too fast. Try again in a minute."}, status=429)
        cache.set(key, count + 1, 60)

        try:
            reply = call_model(messages, config)
        except urllib.error.HTTPError as error:
            detail = ""
            try:
                body = json.loads(error.read().decode("utf-8"))
                body = body[0] if isinstance(body, list) and body else body
                detail = (body.get("error") or {}).get("message", "") if isinstance(body, dict) else ""
            except Exception:  # noqa: BLE001
                pass
            logger.warning("MHTalk AI request failed: %s %s", error.code, detail)
            if error.code in (401, 403) or (error.code == 400 and "key" in detail.lower()):
                message = "The AI key was rejected. Check WHATSUP_AI_API_KEY and WHATSUP_AI_PROVIDER."
            elif error.code == 429:
                message = "The free AI limit was reached for now. Please wait a minute and try again."
            elif error.code == 404:
                message = (
                    f"The AI model \"{config['model']}\" isn't available for this key. "
                    "Set WHATSUP_AI_MODEL in .env to a current model and restart. "
                    f"{detail}"
                ).strip()
            else:
                message = f"The AI service returned an error ({error.code}). {detail}".strip()
            return Response({"detail": message}, status=status.HTTP_502_BAD_GATEWAY)
        except (urllib.error.URLError, TimeoutError, OSError):
            return Response(
                {"detail": "Couldn't reach the AI service. Check the server's internet connection."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"reply": reply or "…"})
