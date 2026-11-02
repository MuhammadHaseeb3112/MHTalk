"""
Group permissions and group invite links.

    PATCH /api/chat/rooms/<id>/permissions/          admins only
    GET   /api/chat/rooms/<id>/invite-link/          code for "Invite via link"
    POST  /api/chat/rooms/<id>/invite-link/reset/    new code, old link stops working
    GET   /api/chat/invite/<code>/                   group preview (rate limited)
    POST  /api/chat/invite/<code>/join/              join the group (rate limited)
"""

import secrets

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import Contact

from .choices import RoomType
from .group_events import PERMISSION_TEXT, post_group_event
from .models import ChatRoom, Participant
from .permissions import can_add_members, group_permissions, is_group_admin
from .utils import broadcast_room_changed

INVITE_PREVIEW_MEMBER_NAMES = 5


def _truthy(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "on", "yes", "admins")


def _member_group(request, pk):
    return get_object_or_404(
        ChatRoom,
        pk=pk,
        room_type=RoomType.GROUP,
        is_active=True,
        participants__user=request.user,
    )


def new_invite_code():
    # ~128 bits of randomness: links cannot be guessed or enumerated.
    return secrets.token_urlsafe(16)


def set_new_invite_code(room):
    """Assign a fresh unique code (retrying on the astronomically rare clash)."""
    for _ in range(5):
        room.invite_code = new_invite_code()
        try:
            with transaction.atomic():
                room.save(update_fields=["invite_code"])
            return room.invite_code
        except IntegrityError:
            continue
    raise IntegrityError("Could not allocate a unique invite code.")


def invite_payload(room):
    return {"room_id": room.id, "code": room.invite_code, "path": f"/join/{room.invite_code}"}


class GroupPermissionsAPIView(APIView):
    """Group info > Group permissions (admins only)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Group permissions", tags=["Chat"])
    def get(self, request, pk):
        room = _member_group(request, pk)
        return Response(group_permissions(room))

    @extend_schema(
        summary="Change group permissions",
        request={"type": "object", "properties": {
            "edit_info_admins_only": {"type": "boolean"},
            "send_messages_admins_only": {"type": "boolean"},
            "add_members_admins_only": {"type": "boolean"},
        }},
        tags=["Chat"],
    )
    def patch(self, request, pk):
        room = _member_group(request, pk)
        if not is_group_admin(request.user, room):
            return Response({"detail": "Only group admins can change group permissions."}, status=status.HTTP_403_FORBIDDEN)
        changed = []
        for field in PERMISSION_TEXT:
            if field not in request.data:
                continue
            value = _truthy(request.data.get(field))
            if getattr(room, field) != value:
                setattr(room, field, value)
                changed.append(field)
        if not changed:
            return Response(group_permissions(room))
        room.save(update_fields=[*changed, "updated_at"])
        for field in changed:
            post_group_event(
                room,
                request.user,
                "permissions_changed",
                PERMISSION_TEXT[field][int(getattr(room, field))],
                request=request,
                setting=field,
                value=getattr(room, field),
            )
        broadcast_room_changed(room.id, "permissions_changed")
        return Response(group_permissions(room))


class GroupInviteLinkAPIView(APIView):
    """The group's invite link (created on first use)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Group invite link", tags=["Chat"])
    def get(self, request, pk):
        room = _member_group(request, pk)
        if not can_add_members(request.user, room):
            return Response({"detail": "Only group admins can share the invite link."}, status=status.HTTP_403_FORBIDDEN)
        if not room.invite_code:
            set_new_invite_code(room)
        return Response(invite_payload(room))


class ResetGroupInviteLinkAPIView(APIView):
    """Revoke the current link and create a new one."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Reset group invite link", request=None, tags=["Chat"])
    def post(self, request, pk):
        room = _member_group(request, pk)
        if not can_add_members(request.user, room):
            return Response({"detail": "Only group admins can reset the invite link."}, status=status.HTTP_403_FORBIDDEN)
        set_new_invite_code(room)
        return Response(invite_payload(room))


class _InviteCodeMixin:
    permission_classes = [IsAuthenticated]
    # Codes are unguessable, but rate-limit lookups anyway (THROTTLE_INVITE).
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invite"

    def get_room(self, code):
        code = str(code or "").strip()
        if not code or len(code) > 64:
            return None
        return (
            ChatRoom.objects.filter(invite_code=code, room_type=RoomType.GROUP, is_active=True)
            .first()
        )

    def not_found(self):
        return Response(
            {"detail": "This invite link is invalid or has been reset."},
            status=status.HTTP_404_NOT_FOUND,
        )


class InvitePreviewAPIView(_InviteCodeMixin, APIView):
    """What the /join/<code> page shows before joining."""

    @extend_schema(summary="Group invite preview", tags=["Chat"])
    def get(self, request, code):
        room = self.get_room(code)
        if room is None:
            return self.not_found()
        members = list(
            Participant.objects.filter(room=room)
            .select_related("user", "user__profile")
            .order_by("-is_admin", "joined_at")
        )
        saved_names = dict(
            Contact.objects.filter(owner=request.user, contact_user_id__in=[m.user_id for m in members])
            .values_list("contact_user_id", "name")
        )
        is_member = any(member.user_id == request.user.id for member in members)
        names = []
        for member in members:
            user = member.user
            if user.is_deleted:
                continue
            if user.pk == request.user.pk:
                names.insert(0, "You")
                continue
            profile = getattr(user, "profile", None)
            names.append(
                (saved_names.get(user.pk) or "").strip()
                or (getattr(profile, "display_name", "") or "").strip()
                or user.phone_number
            )
        return Response({
            "room_id": room.id,
            "name": room.name,
            "description": room.description,
            "photo": request.build_absolute_uri(room.photo.url) if room.photo else None,
            "participants_count": len(members),
            "member_names": names[:INVITE_PREVIEW_MEMBER_NAMES],
            "is_member": is_member,
        })


class InviteJoinAPIView(_InviteCodeMixin, APIView):
    """Join a group through its invite link."""

    @extend_schema(summary="Join group via invite link", request=None, tags=["Chat"])
    def post(self, request, code):
        room = self.get_room(code)
        if room is None:
            return self.not_found()
        participant, created = Participant.objects.get_or_create(room=room, user=request.user)
        if created:
            post_group_event(
                room,
                request.user,
                "joined_via_link",
                "{actor} joined using this group's invite link",
                request=request,
            )
            broadcast_room_changed(room.id, "participant_added")
        return Response(
            {"room_id": room.id, "joined": created, "already_member": not created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
