import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics
from rest_framework import permissions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .lifecycle import schedule_ring_timeout
from .lifecycle import cancel_ring_timeout
from .lifecycle import leave_call

from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
)


from .group import (
    GroupCallError,
    decline_group_call,
    join_group_call,
    leave_group_call,
    start_group_call,
)
from .utils import (
    active_room_call,
    has_active_call,
    room_has_active_call,
    broadcast_call_event,
)

from apps.chat.models import (
    ChatRoom, Message,
)
from apps.chat.serializers import MessageSerializer

from .choices import (
    CallStatus,
    CallType,
)
from apps.chat.choices import RoomType

from .models import (
    Call,
    CallParticipant,
)

from .events import (
    mark_missed_calls_seen,
    notify_calls_changed,
    publish_call_message,
    unseen_missed_count,
)
from .serializers import (
    CallSerializer,
    StartCallSerializer,
)



class StartCallAPIView(APIView):
    """
    Start a new call.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )


    @extend_schema(
        summary="Start Call",
        request=StartCallSerializer,
        description="""
        Start a new audio or video call.

        Only room participants can start a call.
        """,
        responses={
            201: CallSerializer,
            409: OpenApiResponse(description="Active call already exists."),
        },
        tags=["Calls"],
    )

    def post(
        self,
        request,
    ):

        room = get_object_or_404(
            ChatRoom,
            pk=request.data.get("room"),
        )

        if room.room_type == RoomType.GROUP:
            return self.start_group(request, room)

        if room_has_active_call(room):

            return Response(
                {
                    "detail":
                    "A call is already in progress for this room.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        

        if has_active_call(request.user):

            return Response(
                {
                    "detail":
                    "You are already in another call.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        if not room.participants.filter(
            user=request.user,
        ).exists():

            return Response(
                {
                    "detail":
                    "You are not a participant of this room."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        call_type = request.data.get(
            "call_type",
            CallType.AUDIO,
        )

        if call_type not in CallType.values:

            return Response(
                {
                    "detail":
                    "Invalid call type.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        

        participants = list(
            room.participants.select_related("user")
        )

        # Blocking (private chats). If the caller blocked the other person
        # they must unblock first. If the other person blocked the caller the
        # call is created for the caller only: it shows "Calling…" and then
        # "No answer", but never rings, appears in the history or leaves a
        # missed-call card for the person who blocked them (WhatsApp style).
        from apps.chat.utils import has_blocked, sender_has_blocked_peer

        if sender_has_blocked_peer(room, request.user):
            return Response(
                {"detail": "Unblock this contact to call."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if room.room_type == "PRIVATE":
            participants = [
                participant
                for participant in participants
                if participant.user_id == request.user.id
                or not has_blocked(participant.user_id, request.user.id)
            ]

        for participant in participants:

            if has_active_call(participant.user):

                return Response(
                    {
                        "detail":
                        f"{participant.user.phone_number} is already in another call.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        with transaction.atomic():

            call = Call.objects.create(
                room=room,
                caller=request.user,
                call_type=call_type,
            )

            schedule_ring_timeout(
                call.id,
            )

            for participant in participants:

                CallParticipant.objects.create(
                    call=call,
                    user=participant.user,
                )
            

        # Notify each participant through their personal call-inbox group. This
        # works even when the recipient currently has another conversation open.
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            event_payload = {
                "call_id": call.id,
                "caller": request.user.id,
                "room": room.id,
                "call_type": call_type,
            }
            for participant in participants:
                if participant.user_id == request.user.id:
                    continue
                async_to_sync(channel_layer.group_send)(
                    f"user_call_{participant.user_id}",
                    {
                        "type": "call.event",
                        "event": "incoming_call",
                        "payload": event_payload,
                    },
                )

        notify_calls_changed(call, "started")
        # Web Push "Incoming call" for participants with no open tab.
        from apps.notifications.push import notify_incoming_call
        notify_incoming_call(call, [participant.user_id for participant in participants])

        return Response(
            CallSerializer(call, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def start_group(self, request, room):
        """Ring every member of the group; the caller is in the call at once."""
        if not room.participants.filter(user=request.user).exists():
            return Response({"detail": "You are not a participant of this room."}, status=status.HTTP_403_FORBIDDEN)
        call_type = request.data.get("call_type", CallType.AUDIO)
        if call_type not in CallType.values:
            return Response({"detail": "Invalid call type."}, status=status.HTTP_400_BAD_REQUEST)
        active = active_room_call(room)
        if active is not None:
            # The client offers to join the ongoing call instead.
            return Response(
                {"detail": "A group call is already in progress. Join it instead.", "call_id": active.id},
                status=status.HTTP_409_CONFLICT,
            )
        if has_active_call(request.user):
            return Response({"detail": "You are already in another call."}, status=status.HTTP_409_CONFLICT)
        call = start_group_call(room, request.user, call_type)
        notify_calls_changed(call, "started")
        call = Call.objects.prefetch_related("participants__user__profile").select_related("caller__profile", "room").get(pk=call.pk)
        return Response(CallSerializer(call, context={"request": request}).data, status=status.HTTP_201_CREATED)
    

class AcceptCallAPIView(APIView):

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="Accept Call",
        request=None,
        description="Accept an incoming call.",
        responses={
            200: OpenApiResponse(description="Call accepted."),
        },
        tags=["Calls"],
    )

    def post(
        self,
        request,
        pk,
    ):
        

        call = get_object_or_404(
            Call,
            pk=pk,
        )

        if call.is_group:
            # Accept / late join / rejoin. The response lists who is already
            # in the call: the joiner sends each of them a WebRTC offer.
            try:
                others = join_group_call(call, request.user)
            except GroupCallError as error:
                return Response({"detail": error.detail}, status=error.status)
            call = (
                Call.objects.prefetch_related("participants__user__profile")
                .select_related("caller__profile", "room")
                .get(pk=call.pk)
            )
            return Response(
                {
                    "message": "Joined.",
                    "present": others,
                    "call": CallSerializer(call, context={"request": request}).data,
                }
            )

        if not call.participants.filter(
            user=request.user,
        ).exists():

            return Response(
                {
                    "detail":
                    "You are not a participant of this call.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )



        if call.status != CallStatus.RINGING:

            return Response(
                {
                    "detail":
                    "Call is no longer available.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        call.status = CallStatus.ONGOING

        call.answered_at = timezone.now()

        call.save(
            update_fields=[
                "status",
                "answered_at",
            ]
        )

        cancel_ring_timeout(
            call.id,
        )
        notify_calls_changed(call, "accepted")

        return Response(
            {
                "message":
                "Call accepted.",
            }
        )
    

class RejectCallAPIView(APIView):

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="Reject Call",
        request=None,
        description="Reject an incoming call.",
        responses={
            200: OpenApiResponse(description="Call rejected."),
        },
        tags=["Calls"],
    )

    def post(
        self,
        request,
        pk,
    ):
        
        call = get_object_or_404(
            Call,
            pk=pk,
        )

        if not call.participants.filter(
            user=request.user,
        ).exists():

            return Response(
                {
                    "detail":
                    "You are not a participant of this call.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if call.is_group:
            # Declining a group call only stops it ringing for you.
            try:
                decline_group_call(call, request.user)
            except GroupCallError as error:
                return Response({"detail": error.detail}, status=error.status)
            return Response({"message": "Call declined."})

        if call.status != CallStatus.RINGING:

            return Response(
                {
                    "detail":
                    "Call already finished.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        call.status = CallStatus.REJECTED

        call.ended_at = timezone.now()

        call.save(
            update_fields=[
                "status",
                "ended_at",
            ]
        )

        cancel_ring_timeout(
            call.id,
        )
        publish_call_message(call, request)
        notify_calls_changed(call, "rejected")

        return Response(
            {
                "message":
                "Call rejected.",
            }
        )
    

class EndCallAPIView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        summary="End Call",
        request=None,
        description="End a call and add one clickable call summary to the conversation.",
        responses={200: OpenApiResponse(description="Call ended.")},
        tags=["Calls"],
    )
    def post(self, request, pk):
        call = get_object_or_404(Call.objects.select_related("room", "caller"), pk=pk)
        if not call.participants.filter(user=request.user).exists():
            return Response({"detail": "You are not a participant of this call."}, status=status.HTTP_403_FORBIDDEN)

        if call.is_group:
            # Leaving a group call ends it only when <= 1 person remains
            # (leave_group_call publishes the call card in that case).
            call = leave_group_call(call, request.user)
            call.refresh_from_db()
            response_data = {"message": "Left the call.", "call_id": call.id, "status": call.status, "duration": call.duration, "room_id": call.room_id}
            return Response(response_data, status=status.HTTP_200_OK)

        if call.status in (CallStatus.RINGING, CallStatus.ONGOING):
            leave_call(call, request.user)
            cancel_ring_timeout(call.id)
            call.refresh_from_db()
        elif call.status != CallStatus.ENDED:
            return Response({"detail": "This call is no longer active."}, status=status.HTTP_200_OK)

        response_data = {"message": "Call ended.", "call_id": call.id, "status": call.status, "duration": call.duration}
        if call.status == CallStatus.ENDED:
            call_message = publish_call_message(call, request)
            if call_message is not None:
                response_data["call_message"] = MessageSerializer(call_message, context={"request": request}).data
            response_data["room_id"] = call.room_id
            notify_calls_changed(call, "ended")
        return Response(response_data, status=status.HTTP_200_OK)


class CallHistoryAPIView(generics.ListAPIView):

    serializer_class = CallSerializer

    permission_classes = (
        permissions.IsAuthenticated,
    )


    @extend_schema(
        summary="Call History",
        description="Retrieve call history for the authenticated user.",
        responses={
            200: CallSerializer(many=True),
        },
        tags=["Calls"],
    )

    def get_queryset(
        self,
    ):
        queryset = (
            Call.objects.filter(
                participants__user=self.request.user,
            )
            .select_related(
                "caller",
                "caller__profile",
                "room",
            )
            .prefetch_related(
                "participants",
                "participants__user",
                "participants__user__profile",
            )
            .distinct()
            .order_by(
                "-started_at",
            )
        )
        if self.request.query_params.get("missed") in ("1", "true"):
            from django.db.models import Exists, OuterRef, Q

            from .choices import ParticipantState

            # Group calls: missed for me if I never joined and did not decline.
            my_group_miss = CallParticipant.objects.filter(
                call=OuterRef("pk"),
                user=self.request.user,
                answered_at__isnull=True,
            ).exclude(state=ParticipantState.DECLINED)
            queryset = queryset.filter(
                Q(is_group=False, answered_at__isnull=True) | Q(is_group=True) & Exists(my_group_miss)
            ).exclude(caller=self.request.user)
        return queryset


class ActiveCallsAPIView(generics.ListAPIView):
    """
    Group calls that are ringing or ongoing in the user's groups. Drives the
    green "Join" banner in the chat and the "Ongoing call" chat-list row.
    """

    serializer_class = CallSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None

    @extend_schema(summary="Active group calls", responses={200: CallSerializer(many=True)}, tags=["Calls"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return (
            Call.objects.filter(
                is_group=True,
                status__in=(CallStatus.RINGING, CallStatus.ONGOING),
                ended_at__isnull=True,
                room__participants__user=self.request.user,
            )
            .select_related("caller", "caller__profile", "room")
            .prefetch_related("participants", "participants__user", "participants__user__profile")
            .distinct()
            .order_by("-started_at")
        )

class HoldCallAPIView(APIView):

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="Hold Call",
        request=None,
        description="Hold an ongoing call.",
        responses={
            200: OpenApiResponse(description="Call Hold."),
        },
        tags=["Calls"],
    )

    def post(
        self,
        request,
        pk,
    ):

        call = get_object_or_404(
            Call,
            pk=pk,
        )

        if call.status != CallStatus.ONGOING:

            return Response(
                {
                    "detail": "Call is not active.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        participant = get_object_or_404(
            CallParticipant,
            call=call,
            user=request.user,
        )

        if participant.is_on_hold:

            return Response(
                {
                    "detail": "Call is already on hold.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        participant.is_on_hold = True

        participant.save(
            update_fields=[
                "is_on_hold",
            ]
        )

        broadcast_call_event(
            room_id=call.room_id,
            event="hold_call",
            payload={
                "call_id": call.id,
                "user": request.user.id,
            },
        )

        return Response(
            {
                "message": "Call placed on hold.",
            }
        )
    

class ResumeCallAPIView(APIView):

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="Resume Call",
        request=None,
        description="Resume a hold call.",
        responses={
            200: OpenApiResponse(description="Call resume."),
        },
        tags=["Calls"],
    )

    def post(
        self,
        request,
        pk,
    ):

        call = get_object_or_404(
            Call,
            pk=pk,
        )

        if call.status != CallStatus.ONGOING:

            return Response(
                {
                    "detail": "Call is not active.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        participant = get_object_or_404(
            CallParticipant,
            call=call,
            user=request.user,
        )

        if not participant.is_on_hold:

            return Response(
                {
                    "detail": "Call is not on hold.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        participant.is_on_hold = False

        participant.save(
            update_fields=[
                "is_on_hold",
            ]
        )

        broadcast_call_event(
            room_id=call.room_id,
            event="resume_call",
            payload={
                "call_id": call.id,
                "user": request.user.id,
            },
        )

        return Response(
            {
                "message": "Call resumed.",
            }
        )


class MissedCallsAPIView(APIView):
    """
    ``GET``  -> ``{"unseen_count": n}`` for the Calls navigation badge.
    ``POST`` -> acknowledge every missed call (opening the Calls tab).
    """

    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(summary="Unseen missed calls", tags=["Calls"])
    def get(self, request):
        return Response({"unseen_count": unseen_missed_count(request.user)})

    @extend_schema(summary="Acknowledge missed calls", request=None, tags=["Calls"])
    def post(self, request):
        updated = mark_missed_calls_seen(request.user)
        if updated:
            from asgiref.sync import async_to_sync as _a2s

            layer = get_channel_layer()
            if layer is not None:
                _a2s(layer.group_send)(
                    f"chat_inbox_{request.user.id}",
                    {"type": "inbox.call_changed", "action": "missed_seen"},
                )
        return Response({"acknowledged": updated, "unseen_count": 0})


class IceServersAPIView(APIView):
    """
    WebRTC ICE servers for the signed-in user.

    STUN is always included. TURN (needed when both people are behind strict
    NAT, e.g. many mobile networks) is configured on the server so the
    password never ships inside the website's JavaScript:

    * ``TURN_SECRET`` (coturn ``use-auth-secret``): a short-lived username /
      HMAC credential pair is minted per request (TURN REST API scheme).
    * ``TURN_USERNAME`` / ``TURN_PASSWORD``: fixed credentials from a TURN
      provider (Metered, Cloudflare...).
    """

    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(summary="ICE servers for calls", tags=["Calls"])
    def get(self, request):
        import base64
        import hashlib
        import hmac
        import time

        from django.conf import settings

        servers = [{"urls": ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"]}]
        urls = list(getattr(settings, "MHTALK_TURN_URLS", []) or [])
        ttl = int(getattr(settings, "MHTALK_TURN_TTL_SECONDS", 86400))
        if urls and settings.MHTALK_TURN_SECRET:
            username = f"{int(time.time()) + ttl}:{request.user.id}"
            digest = hmac.new(settings.MHTALK_TURN_SECRET.encode(), username.encode(), hashlib.sha1).digest()
            servers.append({"urls": urls, "username": username, "credential": base64.b64encode(digest).decode()})
        elif urls and settings.MHTALK_TURN_USERNAME:
            servers.append({
                "urls": urls,
                "username": settings.MHTALK_TURN_USERNAME,
                "credential": settings.MHTALK_TURN_PASSWORD,
            })
        return Response({"ice_servers": servers, "ttl": ttl})
