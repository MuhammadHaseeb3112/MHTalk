"""Shared helpers for the accounts app."""

import re

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def normalize_phone_variants(value):
    """
    Return the stored-phone candidates for a user-typed number.

    Accepts international (+923001234567), local Pakistani (03001234567),
    and bare (3001234567 / 923001234567) formats. The canonical E.164 form
    is returned first.
    """
    raw = str(value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return []

    normalized = digits
    if normalized.startswith("00"):
        normalized = normalized[2:]
    if normalized.startswith("0") and len(normalized) == 11:
        normalized = "92" + normalized[1:]
    elif len(normalized) == 10 and normalized.startswith("3"):
        normalized = "92" + normalized

    ordered = []
    candidates = [f"+{normalized}", normalized, raw, digits, f"+{digits}"]
    if normalized.startswith("92") and len(normalized) >= 12:
        candidates.append(f"0{normalized[2:]}")
    for item in candidates:
        if item and item not in ordered:
            ordered.append(item)
    return ordered


def notify_profile_changed(user):
    """
    Tell everyone who shares a conversation with ``user`` that their profile
    (name, about, photo) changed so open sidebars refresh without a reload.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    from apps.chat.models import Participant

    room_ids = list(
        Participant.objects.filter(user=user).values_list("room_id", flat=True)
    )
    user_ids = set(
        Participant.objects.filter(room_id__in=room_ids).values_list("user_id", flat=True)
    )
    user_ids.add(user.pk)
    for user_id in user_ids:
        async_to_sync(channel_layer.group_send)(
            f"chat_inbox_{user_id}",
            {"type": "inbox.profile_changed", "user_id": user.pk},
        )


def broadcast_presence_refresh(user):
    """
    Re-send ``user``'s presence after a privacy change. Every receiving
    socket filters it for its own viewer (apps/accounts/privacy.py), so
    people who may no longer see "online"/last seen get it cleared live.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    from apps.chat.models import Participant
    from .models import Profile

    profile = Profile.objects.filter(user=user).only("is_online", "last_seen").first()
    if profile is None:
        return
    payload = {
        "type": "presence.update",
        "user_id": user.pk,
        "is_online": bool(profile.is_online),
        "last_seen": None if profile.is_online or not profile.last_seen else profile.last_seen.isoformat(),
    }
    room_ids = list(Participant.objects.filter(user=user).values_list("room_id", flat=True))
    for room_id in room_ids:
        async_to_sync(channel_layer.group_send)(f"chat_{room_id}", payload)
    peer_ids = set(
        Participant.objects.filter(room_id__in=room_ids).exclude(user=user).values_list("user_id", flat=True)
    )
    for peer_id in peer_ids:
        async_to_sync(channel_layer.group_send)(f"chat_inbox_{peer_id}", {**payload, "type": "inbox.presence"})
