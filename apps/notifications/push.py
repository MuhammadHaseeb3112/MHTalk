"""
Web Push (VAPID) notifications for people who have no MHTalk tab open.

The chat / call code calls one function per event:

    notify_new_message(message, hidden_user_ids)   # apps.chat.utils.broadcast_message
    notify_incoming_call(call, recipient_ids)      # apps.calls.views.StartCallAPIView

Both return immediately. After the surrounding transaction commits, the work
(recipient lookup + HTTP requests to the push services) runs on a small
module-level thread pool, so a slow push service can never block a request
or a websocket handler. Each HTTP request has a 5 s timeout, and
subscriptions the push service reports as gone (404/410) are deleted.

Only users with no open inbox socket (``Profile.active_connections == 0``)
are pushed: anyone with a tab open already gets the in-app / desktop
notification, so this avoids duplicates.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from threading import Lock

from django.conf import settings
from django.db import connections, transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

PUSH_TIMEOUT_SECONDS = 5
MESSAGE_TTL_SECONDS = 24 * 60 * 60
CALL_TTL_SECONDS = 60
BODY_LIMIT = 180
ICON_URL = "/pwa-192.png"
BADGE_URL = "/pwa-badge-96.png"

CALL_EVENT_PREFIX = "__MHTALK_CALL_EVENT__:"
STATUS_REACTION_PREFIX = "__MHTALK_STATUS_REACTION__:"

_executor = None
_executor_lock = Lock()


# ------------------------------------------------------------------ config

def public_key():
    return getattr(settings, "VAPID_PUBLIC_KEY", "") or ""


def push_enabled():
    """True when VAPID keys are configured and pywebpush is installed."""
    if not (public_key() and getattr(settings, "VAPID_PRIVATE_KEY", "")):
        return False
    try:
        import pywebpush  # noqa: F401
    except ImportError:  # pragma: no cover - dependency missing
        return False
    return True


@lru_cache(maxsize=2)
def _vapid(private_key):
    from py_vapid import Vapid

    return Vapid.from_string(private_key=private_key)


def _get_executor():
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webpush")
        return _executor


def _run_in_background(func, *args):
    """Run ``func`` on the push pool (inline when MHTALK_PUSH_INLINE, e.g. tests)."""
    if getattr(settings, "MHTALK_PUSH_INLINE", False):
        func(*args)
        return

    def job():
        try:
            func(*args)
        except Exception:  # never let a push failure surface anywhere
            logger.exception("Web push job failed")
        finally:
            # Worker threads open their own DB connections; give them back.
            connections.close_all()

    try:
        _get_executor().submit(job)
    except RuntimeError:  # interpreter shutting down
        pass


def _after_commit(func, *args):
    if not push_enabled():
        return
    transaction.on_commit(lambda: _run_in_background(func, *args))


# ---------------------------------------------------------------- public API

def notify_new_message(message, hidden_user_ids=()):
    """Queue pushes for a newly broadcast chat message (non-blocking)."""
    if getattr(message, "is_deleted", False):
        return
    _after_commit(_send_message_pushes, message.pk, tuple(sorted(hidden_user_ids or ())))


def notify_incoming_call(call, recipient_ids):
    """Queue "Incoming voice/video call" pushes (non-blocking)."""
    recipients = tuple(sorted({int(uid) for uid in recipient_ids if int(uid) != call.caller_id}))
    if recipients:
        _after_commit(_send_call_pushes, call.pk, recipients)


# ------------------------------------------------------------------ helpers

def _offline_user_ids(user_ids):
    """Users from ``user_ids`` with no open MHTalk socket right now."""
    from apps.accounts.models import Profile

    online = set(
        Profile.objects.filter(user_id__in=user_ids, active_connections__gt=0).values_list("user_id", flat=True)
    )
    return [uid for uid in user_ids if uid not in online]


def _names_for(sender, recipient_ids):
    """How each recipient knows ``sender``: saved contact name > profile name > phone."""
    from apps.accounts.models import Contact

    profile = getattr(sender, "profile", None)
    fallback = (getattr(profile, "display_name", "") or "").strip() or sender.phone_number
    saved = dict(
        Contact.objects.filter(owner_id__in=recipient_ids, contact_user_id=sender.pk)
        .exclude(name="")
        .values_list("owner_id", "name")
    )
    return {uid: saved.get(uid) or fallback for uid in recipient_ids}


def _special_payload(content):
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        return json.loads(content[start:end + 1])
    except ValueError:
        return {}


def _message_text(message):
    """Notification body for a message, like the chat-list preview."""
    from apps.chat.choices import MessageType

    content = (message.content or "").strip()
    if getattr(message, "is_view_once", False):
        # Never reveal a view-once caption in a notification.
        video = message.message_type == MessageType.VIDEO
        return "🎥 View once video" if video else "📷 View once photo"
    if message.message_type == getattr(MessageType, "POLL", "POLL"):
        poll = getattr(message, "poll", None)
        return f"📊 Poll: {poll.question}" if poll is not None else "📊 Poll"
    if getattr(message, "voice_note", None) is not None:
        return "🎤 Voice message"
    attachments = list(message.attachments.all())
    if attachments:
        first = attachments[0]
        mime = (first.mime_type or "").lower()
        name = first.file_name or ""
        if message.message_type == getattr(MessageType, "STICKER", "STICKER"):
            return "🏷️ Sticker"
        if mime.startswith("image/") or message.message_type == MessageType.IMAGE:
            return f"📷 {content}" if content else "📷 Photo"
        if mime.startswith("video/") or message.message_type == MessageType.VIDEO:
            return f"🎥 {content}" if content else "🎥 Video"
        if mime.startswith("audio/"):
            return f"🎵 {name or 'Audio'}"
        return f"📄 {name or 'Document'}"
    if message.message_type == MessageType.LOCATION:
        return "📍 Location"
    if message.message_type == MessageType.CONTACT:
        return "👤 Contact"
    if message.message_type == MessageType.STICKER:
        return "Sticker"
    return content


def _truncate(text):
    text = " ".join(str(text or "").split())
    return text if len(text) <= BODY_LIMIT else text[: BODY_LIMIT - 1] + "…"


def _deliver(subscriptions, payload_for, ttl, urgency="normal"):
    """POST each payload; delete subscriptions the push service says are gone."""
    import pywebpush

    from .models import PushSubscription

    private_key = settings.VAPID_PRIVATE_KEY
    subject = getattr(settings, "VAPID_SUBJECT", "") or "mailto:admin@example.com"
    gone = []
    for subscription in subscriptions:
        payload = payload_for(subscription)
        try:
            pywebpush.webpush(
                subscription_info=subscription.as_subscription_info(),
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=_vapid(private_key),
                vapid_claims={"sub": subject},  # fresh dict: pywebpush adds aud/exp
                ttl=ttl,
                timeout=PUSH_TIMEOUT_SECONDS,
                headers={"Urgency": urgency},
            )
        except pywebpush.WebPushException as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in (404, 410):
                gone.append(subscription.pk)
            else:
                logger.warning("Web push to %s failed: %s", subscription.endpoint[:60], code or exc)
        except Exception as exc:  # network errors, timeouts, bad keys
            logger.warning("Web push to %s failed: %s", subscription.endpoint[:60], exc)
    if gone:
        PushSubscription.objects.filter(pk__in=gone).delete()
    return len(subscriptions) - len(gone)


# --------------------------------------------------------------- the jobs

def _send_message_pushes(message_id, hidden_user_ids):
    from apps.chat.choices import RoomType
    from apps.chat.models import Message, Participant

    from .models import PushSubscription

    message = (
        Message.objects.select_related("room", "sender__profile", "voice_note")
        .prefetch_related("attachments")
        .filter(pk=message_id, is_deleted=False)
        .first()
    )
    if message is None:
        return 0
    room = message.room
    now = timezone.now()
    recipient_ids = list(
        Participant.objects.filter(room_id=room.pk, joined_at__lte=message.created_at)
        .exclude(user_id=message.sender_id)
        .exclude(user_id__in=hidden_user_ids)
        .exclude(user__is_active=False)
        # Muted (forever, or until a time still in the future).
        .exclude(Q(is_muted=True) & (Q(muted_until__isnull=True) | Q(muted_until__gt=now)))
        .values_list("user_id", flat=True)
    )
    # Hidden for anyone who deleted it for themselves in the meantime.
    hidden_now = set(message.deleted_for_users.values_list("user_id", flat=True))
    recipient_ids = [uid for uid in recipient_ids if uid not in hidden_now]
    recipient_ids = _offline_user_ids(recipient_ids)
    if not recipient_ids:
        return 0
    subscriptions = list(PushSubscription.objects.filter(user_id__in=recipient_ids))
    if not subscriptions:
        return 0

    content = message.content or ""
    call_id = None
    if content.startswith(CALL_EVENT_PREFIX):
        event = _special_payload(content)
        if event.get("answered_at"):
            return 0  # finished call: the card is informational, no alert
        video = str(event.get("call_type", "")).upper() == "VIDEO"
        text = "📞 Missed video call" if video else "📞 Missed voice call"
        call_id = event.get("call_id")
    elif content.startswith(STATUS_REACTION_PREFIX):
        event = _special_payload(content)
        if event.get("text"):
            text = f"Replied to your status: {event['text']}"
        else:
            text = f"Reacted {event.get('emoji', '')} to your status".replace("  ", " ")
    elif content.startswith("__MHTALK_GIF__:"):
        text = "GIF"
    elif content.startswith("__MHTALK_"):
        # System notices / group events ("X added Y", disappearing timer...)
        # and any other internal payloads never notify.
        return 0
    else:
        text = _message_text(message)

    names = _names_for(message.sender, recipient_ids)
    is_group = room.room_type == RoomType.GROUP

    def payload_for(subscription):
        base = {
            "type": "message",
            "room_id": room.pk,
            "message_id": message.pk,
            "tag": f"room-{room.pk}",
            "url": f"/?room={room.pk}",
            "icon": ICON_URL,
            "badge": BADGE_URL,
        }
        if call_id:
            base["call_id"] = call_id
        if not subscription.show_previews:
            # Device asked to hide previews: no names, no text.
            return {**base, "title": "MHTalk", "body": "New message"}
        sender_name = names.get(subscription.user_id) or message.sender.phone_number
        if is_group:
            return {**base, "title": room.name or "Group", "body": _truncate(f"{sender_name}: {text}")}
        return {**base, "title": sender_name, "body": _truncate(text)}

    return _deliver(subscriptions, payload_for, MESSAGE_TTL_SECONDS, urgency="high")


def _send_call_pushes(call_id, recipient_ids):
    from apps.calls.choices import CallStatus
    from apps.calls.models import Call
    from apps.chat.choices import RoomType

    from .models import PushSubscription

    call = Call.objects.select_related("room", "caller__profile").filter(pk=call_id).first()
    if call is None or call.status not in (CallStatus.RINGING, CallStatus.ONGOING):
        return 0
    recipient_ids = _offline_user_ids(list(recipient_ids))
    if not recipient_ids:
        return 0
    subscriptions = list(PushSubscription.objects.filter(user_id__in=recipient_ids))
    if not subscriptions:
        return 0
    names = _names_for(call.caller, recipient_ids)
    kind = "video" if str(call.call_type).upper() == "VIDEO" else "voice"
    is_group = bool(getattr(call, "is_group", False)) or call.room.room_type == RoomType.GROUP
    if is_group:
        kind = f"group {kind}"

    def payload_for(subscription):
        base = {
            "type": "call",
            "room_id": call.room_id,
            "call_id": call.pk,
            "tag": f"call-{call.pk}",
            "url": f"/?room={call.room_id}",
            "icon": ICON_URL,
            "badge": BADGE_URL,
            "require_interaction": True,
        }
        if not subscription.show_previews:
            return {**base, "title": "MHTalk", "body": f"Incoming {kind} call"}
        caller = names.get(subscription.user_id) or call.caller.phone_number
        title = (call.room.name or "Group") if is_group else caller
        return {**base, "title": title, "body": f"Incoming {kind} call from {caller}"}

    return _deliver(subscriptions, payload_for, CALL_TTL_SECONDS, urgency="high")
