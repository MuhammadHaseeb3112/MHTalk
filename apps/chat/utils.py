from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.db import transaction

from .serializers import MessageSerializer
from django.db.models import Q

from .choices import RoomType
from .models import (
    Attachment,
    BlockedUser,
    ChatRoom,
    DeletedMessage,
    Message,
    MessageReceipt,
    Participant,
    Reaction,
    StarredMessage,
    VoiceNote,
)


# ---------------------------------------------------------------- blocking
#
# WhatsApp behaviour: when A blocks B, B is not told. B can still "send":
# the message stays on one grey tick forever and A never receives it (not
# even after unblocking). B's calls keep showing "Calling…" and never ring
# for A. A cannot message or call B until A unblocks. Groups are unaffected.

def has_blocked(blocker_id, other_id):
    """True when ``blocker_id`` has blocked ``other_id``."""
    if not blocker_id or not other_id:
        return False
    return BlockedUser.objects.filter(blocked_by_id=blocker_id, blocked_user_id=other_id).exists()


def blocked_user_ids(user_id):
    """Everyone with a block in either direction with ``user_id``."""
    rows = BlockedUser.objects.filter(Q(blocked_by_id=user_id) | Q(blocked_user_id=user_id)).values_list(
        "blocked_by_id", "blocked_user_id"
    )
    ids = set()
    for blocker, blocked in rows:
        ids.add(blocked if blocker == user_id else blocker)
    return ids


def private_peer_id(room_or_id, user_id):
    """The other member of a private chat (None for groups / missing)."""
    room_id = getattr(room_or_id, "pk", room_or_id)
    room_type = getattr(room_or_id, "room_type", None)
    if room_type is None:
        room_type = ChatRoom.objects.filter(pk=room_id).values_list("room_type", flat=True).first()
    if room_type != RoomType.PRIVATE:
        return None
    return (
        Participant.objects.filter(room_id=room_id)
        .exclude(user_id=user_id)
        .values_list("user_id", flat=True)
        .first()
    )


def sender_has_blocked_peer(room, user):
    """The sender blocked the other person: sending must be refused."""
    peer_id = private_peer_id(room, getattr(user, "pk", user))
    return bool(peer_id) and has_blocked(getattr(user, "pk", user), peer_id)


def hide_from_blockers(message):
    """
    Hide a new private-chat message from a recipient who has blocked the
    sender. The hidden copy never gets a receipt, so the sender keeps a
    single tick. Returns the set of user ids it is hidden from.
    """
    peer_id = private_peer_id(message.room_id, message.sender_id)
    if peer_id and has_blocked(peer_id, message.sender_id):
        DeletedMessage.objects.get_or_create(message_id=message.pk, user_id=peer_id)
        return {peer_id}
    return set()


def hidden_user_ids(message_id):
    return set(DeletedMessage.objects.filter(message_id=message_id).values_list("user_id", flat=True))


def broadcast_room_changed(room_id, action="updated", extra_user_ids=()):
    """Tell connected users to refresh the sidebar/details for a room change."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    user_ids = set(Participant.objects.filter(room_id=room_id).values_list("user_id", flat=True))
    user_ids.update(int(user_id) for user_id in (extra_user_ids or ()) if user_id is not None)
    for user_id in user_ids:
        async_to_sync(channel_layer.group_send)(
            f"chat_inbox_{user_id}",
            {"type": "inbox.room_changed", "room_id": int(room_id), "action": action},
        )


def touch_room_for_message(message_or_id):
    """Keep sidebar ordering correct after text, media, voice or forwarded messages."""
    message_id = getattr(message_or_id, "pk", message_or_id)
    message = message_or_id if hasattr(message_or_id, "room_id") and hasattr(message_or_id, "created_at") else Message.objects.only("room_id", "created_at").get(pk=message_id)
    ChatRoom.objects.filter(pk=message.room_id).update(updated_at=message.created_at)


def ensure_message_receipts_for_message(message_or_id):
    """Create a pending receipt row for every recipient of a message (1 insert)."""
    message_id = getattr(message_or_id, "pk", message_or_id)
    message = Message.objects.only("id", "room_id", "sender_id", "created_at").get(pk=message_id)
    recipient_ids = list(
        Participant.objects.filter(room_id=message.room_id, joined_at__lte=message.created_at)
        .exclude(user_id=message.sender_id)
        .values_list("user_id", flat=True)
    )
    MessageReceipt.objects.bulk_create(
        [MessageReceipt(message_id=message.id, recipient_id=uid) for uid in recipient_ids],
        ignore_conflicts=True,
    )
    return recipient_ids


def persist_receipts_bulk(message_ids, recipient_id, receipt_type):
    """Persist one recipient's delivered/read state for many messages at once.

    Runs a fixed number of queries no matter how many messages or group
    members are involved (the old per-message loop was O(messages x members)).

    For group conversations the aggregate ticks on ``Message`` only advance
    when every recipient who belonged to the room when the message was sent
    has reached that state. Per-recipient rows stay the source of truth for
    Message info. Returns one result dict per accepted message, oldest first.
    """
    from django.utils import timezone

    ids = [int(value) for value in message_ids if value]
    if not ids:
        return []
    messages = list(
        Message.objects.filter(
            pk__in=ids,
            is_deleted=False,
            room__participants__user_id=recipient_id,
        )
        .exclude(sender_id=recipient_id)
        # hidden for this person (e.g. sent while they had the sender blocked)
        .exclude(deleted_for_users__user_id=recipient_id)
        .only("id", "room_id", "sender_id", "created_at", "is_delivered", "is_read")
        .order_by("created_at", "id")
        .distinct()
    )
    if not messages:
        return []
    now = timezone.now()
    message_ids = [message.id for message in messages]

    # Recipients at send time = members who had joined by then (minus sender).
    room_ids = {message.room_id for message in messages}
    members = {}
    for room_id, user_id, joined_at in Participant.objects.filter(room_id__in=room_ids).values_list(
        "room_id", "user_id", "joined_at"
    ):
        members.setdefault(room_id, []).append((user_id, joined_at))
    recipients_of = {
        message.id: {
            uid for uid, joined_at in members.get(message.room_id, ())
            if uid != message.sender_id and joined_at <= message.created_at
        }
        for message in messages
    }
    MessageReceipt.objects.bulk_create(
        [
            MessageReceipt(message_id=message_id, recipient_id=uid)
            for message_id, uids in recipients_of.items()
            for uid in (uids | {recipient_id})
        ],
        ignore_conflicts=True,
    )

    # This recipient's own state.
    MessageReceipt.objects.filter(
        message_id__in=message_ids, recipient_id=recipient_id, delivered_at__isnull=True
    ).update(delivered_at=now)
    if receipt_type == "read":
        MessageReceipt.objects.filter(
            message_id__in=message_ids, recipient_id=recipient_id, read_at__isnull=True
        ).update(read_at=now)

    # Aggregate ticks.
    state = {}
    for message_id, uid, delivered_at, read_at in MessageReceipt.objects.filter(
        message_id__in=message_ids
    ).values_list("message_id", "recipient_id", "delivered_at", "read_at"):
        state[(message_id, uid)] = (delivered_at, read_at)
    to_deliver, to_undeliver, to_read, to_unread = [], [], [], []
    results = []
    for message in messages:
        uids = recipients_of[message.id]
        all_delivered = bool(uids) and all((state.get((message.id, uid)) or (None, None))[0] for uid in uids)
        all_read = bool(uids) and all((state.get((message.id, uid)) or (None, None))[1] for uid in uids)
        if bool(message.is_delivered) != all_delivered:
            (to_deliver if all_delivered else to_undeliver).append(message.id)
        if bool(message.is_read) != all_read:
            (to_read if all_read else to_unread).append(message.id)
        results.append({
            "message_id": message.id, "room_id": message.room_id, "sender_id": message.sender_id,
            "recipient_id": recipient_id, "receipt": receipt_type,
            "is_delivered": all_delivered, "is_read": all_read,
        })
    if to_deliver:
        Message.objects.filter(pk__in=to_deliver).update(is_delivered=True, delivered_at=now)
    if to_undeliver:
        Message.objects.filter(pk__in=to_undeliver).update(is_delivered=False, delivered_at=None)
    if to_read:
        Message.objects.filter(pk__in=to_read).update(is_read=True, read_at=now)
    if to_unread:
        Message.objects.filter(pk__in=to_unread).update(is_read=False, read_at=None)
    return results


def persist_message_receipt(message_id, recipient_id, receipt_type):
    """Single-message form of :func:`persist_receipts_bulk` (None if rejected)."""
    results = persist_receipts_bulk([message_id], recipient_id, receipt_type)
    return results[0] if results else None


def broadcast_message(
    message,
    request=None,
):
    """
    Broadcast a message to all websocket clients.

    Room subscribers receive ``chat.message``; every participant's inbox
    (including the sender's other tabs) receives ``inbox.message`` so chat
    lists, unread badges and archived counters update without a reload.
    People the message is hidden from (they blocked the sender, or deleted it
    for themselves) are skipped.
    """

    channel_layer = get_channel_layer()

    hide_from_blockers(message)
    ensure_message_receipts_for_message(message)
    touch_room_for_message(message)
    hidden = hidden_user_ids(message.pk)
    # Refresh the aggregate flags before serializing; delivery/read is per-recipient.
    message.refresh_from_db()
    # Serialized once for every recipient, so the sender is shown as the
    # public sees them (privacy settings), not as the sender sees themselves.
    serialized = MessageSerializer(message, context={"request": request, "public_view": True}).data
    # Web Push for recipients with no open tab (non-blocking, after commit).
    from apps.notifications.push import notify_new_message
    notify_new_message(message, hidden)
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"chat_{message.room_id}",
        {"type": "chat.message", "message": serialized, "hidden_for": sorted(hidden)},
    )
    participant_ids = Participant.objects.filter(room_id=message.room_id).values_list("user_id", flat=True)
    for participant_id in participant_ids:
        if participant_id in hidden:
            continue
        async_to_sync(channel_layer.group_send)(
            f"chat_inbox_{participant_id}",
            {"type": "inbox.message", "room_id": message.room_id, "message": dict(serialized)},
        )

def get_message_with_relations(message_id):
    from .serializers import with_message_relations

    return with_message_relations(Message.objects.all()).get(pk=message_id)


def broadcast_deleted_message(message_or_id):
    """Notify chat participants and inboxes that a message was deleted for everyone."""
    message_id = getattr(message_or_id, "pk", message_or_id)
    message = Message.objects.filter(pk=message_id).only("id", "room_id").first()
    if message is None:
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        f"chat_{message.room_id}",
        {"type": "message.deleted", "message_id": int(message.id)},
    )
    broadcast_room_changed(message.room_id, action="message_deleted")


def _delete_unreferenced_files(paths):
    """Remove stored files that no remaining attachment/voice note references."""
    from django.core.files.storage import default_storage

    for path in set(paths):
        if not path:
            continue
        still_used = (
            Attachment.objects.filter(file=path).exists()
            or VoiceNote.objects.filter(audio=path).exists()
        )
        if still_used:
            continue
        try:
            default_storage.delete(path)
        except Exception:
            # Storage cleanup is best-effort; the database tombstone is what matters.
            pass


def soft_delete_messages_for_everyone(messages):
    """Soft-delete messages and broadcast the deletion to connected participants.

    The message row is kept as a tombstone so clients can render
    "This message was deleted". Body, attachments, voice note, reactions,
    stars and pin state are removed; stored files are deleted after commit
    unless a forwarded copy still references them.

    Callers are responsible for authorization and transaction boundaries.
    """
    message_ids = [
        int(getattr(message, "pk", message))
        for message in messages
        if getattr(message, "pk", message) is not None
    ]
    if not message_ids:
        return []

    from django.utils import timezone
    now = timezone.now()
    records = list(
        Message.objects.filter(pk__in=message_ids, is_deleted=False)
        .only("id", "room_id")
    )
    updated_ids = [record.id for record in records]
    if updated_ids:
        file_paths = list(
            Attachment.objects.filter(message_id__in=updated_ids).values_list("file", flat=True)
        ) + list(
            VoiceNote.objects.filter(message_id__in=updated_ids).values_list("audio", flat=True)
        )
        Attachment.objects.filter(message_id__in=updated_ids).delete()
        VoiceNote.objects.filter(message_id__in=updated_ids).delete()
        Reaction.objects.filter(message_id__in=updated_ids).delete()
        StarredMessage.objects.filter(message_id__in=updated_ids).delete()
        Message.objects.filter(pk__in=updated_ids, is_deleted=False).update(
            is_deleted=True,
            is_edited=False,
            is_pinned=False,
            pinned_at=None,
            content="",
            updated_at=now,
        )
        transaction.on_commit(lambda: _delete_unreferenced_files(file_paths))
        for record in records:
            broadcast_deleted_message(record.id)
    return updated_ids


def mark_room_read(room_id, user):
    """
    Mark every visible incoming message in ``room_id`` as read by ``user``.

    Returns the receipt results (one per message whose state changed) so
    callers can notify senders. This is the authoritative REST path used
    when a conversation is opened, instead of one WebSocket frame per message.
    """
    from .serializers import unread_messages_for_user

    unread_ids = list(
        unread_messages_for_user(Message.objects.filter(room_id=room_id), user)
        .order_by("created_at")
        .values_list("id", flat=True)[:500]
    )
    return persist_receipts_bulk(unread_ids, user.id, "read")


def broadcast_receipts(results):
    """Push read/delivered updates to the room and to each sender's inbox."""
    from apps.accounts.privacy import mask_receipt_results

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    # Private chats where read receipts are off only ever show grey ticks.
    for result in mask_receipt_results(results):
        handler_type = "message.read" if result["receipt"] == "read" else "message.delivered"
        async_to_sync(channel_layer.group_send)(
            f"chat_{result['room_id']}",
            {
                "type": handler_type,
                "message_id": result["message_id"],
                "sender_id": result["sender_id"],
                "is_delivered": result["is_delivered"],
                "is_read": result["is_read"],
            },
        )
        async_to_sync(channel_layer.group_send)(
            f"chat_inbox_{result['sender_id']}",
            {
                "type": "inbox.receipt",
                "room_id": result["room_id"],
                "message_id": result["message_id"],
                "receipt": result["receipt"],
                "is_delivered": result["is_delivered"],
                "is_read": result["is_read"],
            },
        )


def notify_user_rooms_changed(user_id, action="updated", room_id=None):
    """Tell one user's open tabs that their own chat-list state changed."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"chat_inbox_{user_id}",
        {"type": "inbox.room_changed", "room_id": room_id, "action": action},
    )

