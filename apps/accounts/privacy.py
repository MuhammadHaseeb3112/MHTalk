"""
Privacy settings (Settings > Privacy), enforced on the server.

WhatsApp rules implemented here:

* Last seen, profile photo and about can each be shown to Everyone, My
  contacts or Nobody. "My contacts" means the *viewer* is in the *owner's*
  saved contacts.
* Online can be Everyone or "Same as last seen".
* Reciprocity: if you don't share your last seen (or online) with someone,
  you can't see theirs either.
* Read receipts: when either side of a private chat turned them off, no blue
  ticks are shown in that chat (both directions). Groups always send them.

Every place that sends profile data to a client goes through
:func:`apply_user_privacy` (``UserSerializer`` does it automatically) or the
presence / receipt helpers below. A serializer without a known viewer (for
example a payload broadcast to many sockets) only exposes what the owner
shares with *Everyone* and never exposes presence.

Contact relations are loaded lazily, at most once per request, so list
endpoints keep a constant number of queries.
"""

from .models import Contact, Profile

EVERYONE = Profile.PRIVACY_EVERYONE
CONTACTS = Profile.PRIVACY_CONTACTS
NOBODY = Profile.PRIVACY_NOBODY

DELETED_ACCOUNT_NAME = "Deleted account"


class PrivacyViewer:
    """Who is looking, plus their (lazily loaded) contact relations."""

    def __init__(self, viewer=None):
        self.viewer = viewer if viewer is not None and getattr(viewer, "is_authenticated", False) else None
        self._saved_me = None
        self._my_contacts = None
        self._profile = None

    @property
    def viewer_id(self):
        return self.viewer.pk if self.viewer is not None else None

    @property
    def profile(self):
        if self.viewer is None:
            return None
        if self._profile is None:
            self._profile = getattr(self.viewer, "profile", None)
        return self._profile

    def saved_me(self):
        """Ids of users who have the viewer in their saved contacts."""
        if self._saved_me is None:
            self._saved_me = set(
                Contact.objects.filter(contact_user_id=self.viewer_id).values_list("owner_id", flat=True)
            ) if self.viewer_id else set()
        return self._saved_me

    def my_contacts(self):
        """Ids of users the viewer saved in their own contacts."""
        if self._my_contacts is None:
            self._my_contacts = set(
                Contact.objects.filter(owner_id=self.viewer_id).values_list("contact_user_id", flat=True)
            ) if self.viewer_id else set()
        return self._my_contacts


def viewer_from_context(context):
    """
    Resolve (and cache) the PrivacyViewer for a serializer context.

    ``context["viewer"]`` wins (used by login/register, where the request is
    anonymous); otherwise ``context["request"].user``. The cache lives on the
    request object so every serializer of one request shares it.
    """
    context = context if context is not None else {}
    cached = context.get("_privacy_viewer")
    if cached is not None:
        return cached
    request = context.get("request")
    explicit = context.get("viewer")
    if context.get("public_view"):
        # One payload fanned out to many sockets: show only what the owner
        # shares with everyone, and no presence.
        ctx = PrivacyViewer(None)
    elif explicit is not None:
        ctx = PrivacyViewer(explicit)
    elif request is not None:
        ctx = getattr(request, "_privacy_viewer", None)
        if ctx is None:
            ctx = PrivacyViewer(getattr(request, "user", None))
            try:
                request._privacy_viewer = ctx
            except AttributeError:
                pass
    else:
        ctx = PrivacyViewer(None)
    try:
        context["_privacy_viewer"] = ctx
    except TypeError:
        pass
    return ctx


# ------------------------------------------------------------------ rules

def _owner_allows(setting, owner_id, ctx):
    """Owner's ``setting`` lets the viewer see the value."""
    if setting == EVERYONE:
        return True
    if setting == CONTACTS and ctx.viewer_id:
        return owner_id in ctx.saved_me()
    return False


def _viewer_allows(setting, owner_id, ctx):
    """Viewer's own ``setting`` shares the value with the owner (reciprocity)."""
    if setting == EVERYONE:
        return True
    if setting == CONTACTS:
        return owner_id in ctx.my_contacts()
    return False


def can_see_photo(owner_profile, owner_id, ctx):
    if ctx.viewer_id == owner_id:
        return True
    return _owner_allows(getattr(owner_profile, "photo_privacy", EVERYONE), owner_id, ctx)


def can_see_about(owner_profile, owner_id, ctx):
    if ctx.viewer_id == owner_id:
        return True
    return _owner_allows(getattr(owner_profile, "about_privacy", EVERYONE), owner_id, ctx)


def can_see_last_seen(owner_profile, owner_id, ctx):
    if ctx.viewer_id is None:
        return False
    if ctx.viewer_id == owner_id:
        return True
    if not _owner_allows(getattr(owner_profile, "last_seen_privacy", EVERYONE), owner_id, ctx):
        return False
    own = ctx.profile
    return _viewer_allows(getattr(own, "last_seen_privacy", EVERYONE), owner_id, ctx)


def can_see_online(owner_profile, owner_id, ctx):
    if ctx.viewer_id is None:
        return False
    if ctx.viewer_id == owner_id:
        return True

    def shares_online(profile, allows):
        if getattr(profile, "online_privacy", EVERYONE) == EVERYONE:
            return True
        return allows(getattr(profile, "last_seen_privacy", EVERYONE), owner_id, ctx)

    return shares_online(owner_profile, _owner_allows) and shares_online(ctx.profile, _viewer_allows)


def privacy_settings(profile):
    return {
        "last_seen": profile.last_seen_privacy,
        "online": profile.online_privacy,
        "profile_photo": profile.photo_privacy,
        "about": profile.about_privacy,
        "read_receipts": bool(profile.read_receipts),
    }


def apply_user_privacy(data, user, ctx):
    """
    Mask a serialized user dict (``UserSerializer`` shape) in place for the
    viewer in ``ctx``. Returns ``data``.
    """
    if not isinstance(data, dict):
        return data
    profile_data = data.get("profile")
    profile = getattr(user, "profile", None)
    owner_id = user.pk

    if getattr(user, "is_deleted", False):
        data["is_deleted"] = True
        data["phone_number"] = ""
        data["email"] = None
        if isinstance(profile_data, dict):
            profile_data.update({
                "display_name": DELETED_ACCOUNT_NAME,
                "profile_picture": None,
                "about": "",
                "is_online": False,
                "last_seen": None,
            })
        return data

    if ctx.viewer_id == owner_id:
        if profile is not None:
            data["privacy"] = privacy_settings(profile)
        return data

    if not isinstance(profile_data, dict) or profile is None:
        return data
    if not can_see_photo(profile, owner_id, ctx):
        profile_data["profile_picture"] = None
    if not can_see_about(profile, owner_id, ctx):
        profile_data["about"] = ""
    if not can_see_online(profile, owner_id, ctx):
        profile_data["is_online"] = False
    if not can_see_last_seen(profile, owner_id, ctx):
        profile_data["last_seen"] = None
    return data


# --------------------------------------------------------------- presence

def presence_for_viewer(owner_id, viewer_id, is_online, last_seen):
    """
    Presence of ``owner_id`` as ``viewer_id`` may see it (used by sockets).
    Returns ``(is_online, last_seen)``; hidden values become False / None.
    """
    from .models import User

    owner = User.objects.select_related("profile").filter(pk=owner_id).first()
    viewer = User.objects.select_related("profile").filter(pk=viewer_id).first()
    if owner is None or viewer is None:
        return False, None
    if owner.is_deleted:
        return False, None
    ctx = PrivacyViewer(viewer)
    profile = getattr(owner, "profile", None)
    online_ok = can_see_online(profile, owner_id, ctx)
    last_seen_ok = can_see_last_seen(profile, owner_id, ctx)
    if is_online and not online_ok:
        # Hide "online": show the last-seen time instead when that is allowed.
        is_online = False
        last_seen = profile.last_seen.isoformat() if last_seen_ok and profile and profile.last_seen else None
    elif not is_online and not last_seen_ok:
        last_seen = None
    return bool(is_online), last_seen


def presence_snapshot_for(viewer, rows):
    """
    Filter presence rows (dicts with user_id / is_online / last_seen /
    profile) for ``viewer`` in a fixed number of queries.
    """
    ctx = PrivacyViewer(viewer)
    result = []
    for row in rows:
        profile = row["profile"]
        online_ok = can_see_online(profile, row["user_id"], ctx)
        last_seen_ok = can_see_last_seen(profile, row["user_id"], ctx)
        is_online = bool(row["is_online"]) and online_ok
        last_seen = row["last_seen"] if (not is_online and last_seen_ok) else None
        result.append({"user_id": row["user_id"], "is_online": is_online, "last_seen": last_seen})
    return result


# ---------------------------------------------------------- read receipts

def receipts_hidden_room_ids(room_ids):
    """
    Private chats (among ``room_ids``) where at least one member turned read
    receipts off: blue ticks are not shown there, in either direction.
    """
    from apps.chat.choices import RoomType
    from apps.chat.models import Participant

    room_ids = {int(room_id) for room_id in room_ids if room_id}
    if not room_ids:
        return set()
    return set(
        Participant.objects.filter(
            room_id__in=room_ids,
            room__room_type=RoomType.PRIVATE,
            user__profile__read_receipts=False,
        ).values_list("room_id", flat=True)
    )


def receipts_hidden_rooms_for_viewer(ctx):
    """
    All private chats of the viewer where blue ticks are hidden (one query,
    cached on the PrivacyViewer). ``None`` when there is no viewer.
    """
    if ctx.viewer_id is None:
        return None
    cached = getattr(ctx, "_receipts_hidden", None)
    if cached is None:
        from apps.chat.choices import RoomType
        from apps.chat.models import Participant

        cached = set(
            Participant.objects.filter(
                room__participants__user_id=ctx.viewer_id,
                room__room_type=RoomType.PRIVATE,
                user__profile__read_receipts=False,
            ).values_list("room_id", flat=True)
        )
        ctx._receipts_hidden = cached
    return cached


def mask_read_state(data, room_id, ctx):
    """Hide blue ticks on a serialized message when receipts are off."""
    if not isinstance(data, dict) or not data.get("is_read"):
        return data
    hidden = receipts_hidden_rooms_for_viewer(ctx)
    if hidden is None:
        hidden = receipts_hidden_room_ids([room_id])
    if room_id in hidden:
        data["is_read"] = False
        data["read_at"] = None
    return data


def mask_receipt_results(results):
    """
    Turn "read" receipt results into "delivered" ones for private chats where
    read receipts are off, so the sender never sees blue ticks there. The
    reader's own state (unread counter) is unaffected.
    """
    hidden = receipts_hidden_room_ids({result["room_id"] for result in results})
    if not hidden:
        return results
    masked = []
    for result in results:
        if result["room_id"] in hidden:
            result = {**result, "receipt": "delivered", "is_read": False}
        masked.append(result)
    return masked
