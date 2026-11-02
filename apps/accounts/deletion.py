"""
Settings > Account > Delete my account.

Like WhatsApp, deleting an account:

* removes the profile photo, about and every status update,
* deletes the user's saved contacts (and other people's saved entries for
  this number, so the number can be registered again by someone new),
  blocks and push subscriptions (when that feature is installed),
* removes the user from every group (members see "X left"),
* keeps other people's chat history readable: the user row stays (so
  messages keep their sender) but is anonymised and shown as
  "Deleted account"; the phone number is released for re-registration,
* signs out every session (refresh tokens blacklisted, sockets closed).
"""

import secrets

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from .models import Contact, Profile
from .privacy import DELETED_ACCOUNT_NAME


def _released_phone_number(user):
    # Not a valid phone number (no "+"), unique, fits max_length=20.
    return f"deleted-{user.pk}-{secrets.token_hex(3)}"[:20]


def _delete_file(field):
    try:
        if field:
            field.delete(save=False)
    except Exception:
        # Storage cleanup is best effort; the database state is what matters.
        pass


def _leave_groups(user):
    """Remove the user from every group (promoting an admin when needed)."""
    from apps.chat.choices import RoomType
    from apps.chat.group_events import post_group_event
    from apps.chat.models import Participant
    from apps.chat.utils import broadcast_room_changed

    memberships = list(
        Participant.objects.filter(user=user, room__room_type=RoomType.GROUP).select_related("room")
    )
    for membership in memberships:
        room = membership.room
        others = Participant.objects.filter(room=room).exclude(pk=membership.pk)
        if membership.is_admin and not others.filter(is_admin=True).exists():
            successor = others.order_by("joined_at").first()
            if successor is not None:
                successor.is_admin = True
                successor.save(update_fields=["is_admin"])
        if others.exists():
            post_group_event(room, user, "left", "{actor} left")
        membership.delete()
        broadcast_room_changed(room.pk, "participant_left", extra_user_ids=[user.pk])


def _delete_statuses(user):
    from apps.status.models import Status

    for status in Status.objects.filter(user=user):
        _delete_file(getattr(status, "media", None))
    Status.objects.filter(user=user).delete()


def _delete_push_subscriptions(user):
    """Delete push subscriptions if a push feature is installed."""
    for model in django_apps.get_models():
        if model.__name__ != "PushSubscription":
            continue
        field = next(
            (f for f in model._meta.get_fields() if getattr(f, "related_model", None) is type(user) and f.many_to_one),
            None,
        )
        if field is not None:
            model.objects.filter(**{field.name: user}).delete()


def _blacklist_refresh_tokens(user):
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


def _notify_signed_out(user_id, peer_ids):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    send = async_to_sync(channel_layer.group_send)
    # Close every open tab of the deleted account.
    send(f"chat_inbox_{user_id}", {"type": "inbox.account_deleted"})
    # Everyone who chatted with them refreshes names/photos.
    for peer_id in peer_ids:
        send(f"chat_inbox_{peer_id}", {"type": "inbox.profile_changed", "user_id": user_id})


def delete_account(user):
    """Delete ``user``'s account (see module docstring)."""
    from apps.chat.models import BlockedUser, Participant, Reaction, StarredMessage

    with transaction.atomic():
        _leave_groups(user)
        _delete_statuses(user)
        Contact.objects.filter(owner=user).delete()
        Contact.objects.filter(contact_user=user).delete()
        BlockedUser.objects.filter(blocked_by=user).delete()
        BlockedUser.objects.filter(blocked_user=user).delete()
        _delete_push_subscriptions(user)
        Reaction.objects.filter(user=user).delete()
        StarredMessage.objects.filter(user=user).delete()

        # Use the cached ``user.profile`` (if any) so the User post_save
        # signal, which saves ``user.profile``, can't write stale values back.
        try:
            profile = user.profile
        except Profile.DoesNotExist:
            profile = None
        if profile is not None:
            _delete_file(profile.profile_picture)
            profile.profile_picture = None
            profile.display_name = DELETED_ACCOUNT_NAME
            profile.about = ""
            profile.is_online = False
            profile.active_connections = 0
            profile.last_seen = timezone.now()
            profile.last_seen_privacy = Profile.PRIVACY_NOBODY
            profile.online_privacy = Profile.ONLINE_SAME_AS_LAST_SEEN
            profile.photo_privacy = Profile.PRIVACY_NOBODY
            profile.about_privacy = Profile.PRIVACY_NOBODY
            profile.save()

        user.phone_number = _released_phone_number(user)
        user.email = None
        user.is_active = False
        user.is_deleted = True
        user.set_unusable_password()
        user.save()

        _blacklist_refresh_tokens(user)

        peer_ids = set(
            Participant.objects.filter(room__participants__user=user)
            .exclude(user=user)
            .values_list("user_id", flat=True)
        )
        user_id = user.pk
        transaction.on_commit(lambda: _notify_signed_out(user_id, peer_ids))
