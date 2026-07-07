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


from .utils import (
    has_active_call,
    room_has_active_call,
    broadcast_call_event,
)

from apps.chat.models import (
    ChatRoom,
)

from .choices import (
    CallStatus,
    CallType,
)

from .models import (
    Call,
    CallParticipant,
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
            

        return Response(
            CallSerializer(call).data,
            status=status.HTTP_201_CREATED,
        )
    

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

        return Response(
            {
                "message":
                "Call rejected.",
            }
        )
    

class EndCallAPIView(APIView):

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="End Call",
        request=None,
        description="End an ongoing call.",
        responses={
            200: OpenApiResponse(description="Call ended."),
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

        if call.status not in (
            CallStatus.RINGING,
            CallStatus.ONGOING,
        ):

            return Response(
                {
                    "detail":
                    "Call already ended.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


        leave_call(
            call,
            request.user,
        )

        cancel_ring_timeout(
            call.id,
        )


        return Response(
            {
                "message":
                "Call ended.",
            }
        )
    


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

        return (
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