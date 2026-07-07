import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .presence import CALL_CHANNELS
from apps.chat.models import Participant
from .choices import CallType
from django.utils import timezone
from .lifecycle import cancel_ring_timeout

from .models import Call
from .lifecycle import leave_call
from .choices import CallStatus



logger = logging.getLogger(__name__)


class CallConsumer(AsyncJsonWebsocketConsumer):
    """
    WebRTC signaling consumer.

    Responsible only for exchanging signaling messages.

    Audio/video is transmitted directly between peers
    using WebRTC.
    """

    async def connect(self):

        self.user = self.scope["user"]

        if self.user.is_anonymous:

            await self.close(code=4001)
            return

        self.room_id = int(
            self.scope["url_route"]["kwargs"]["room_id"]
        )

        self.room_group_name = f"call_{self.room_id}"

        is_member = await self.is_room_participant()

        if not is_member:

            await self.close(code=4003)
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        await self.accept()

        CALL_CHANNELS[self.user.id] = self.channel_name


        await self.broadcast(
            "participant_joined",
            {
                "call_id": None,
                "user": self.user.id,
            },
        )


        logger.info(
            "User %s connected to call room %s",
            self.user.id,
            self.room_id,
        )

    async def disconnect(
        self,
        close_code,
    ):

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name,
        )

        logger.info(
            "User %s disconnected from call room %s",
            self.user.id,
            self.room_id,
        )

        await self.mark_left()

        CALL_CHANNELS.pop(
            self.user.id,
            None,
        )


        await self.broadcast(
            "participant_left",
            {
                "room": self.room_id,
                "user": self.user.id,
            },
        )

    @database_sync_to_async
    def is_room_participant(
        self,
    ):

        return Participant.objects.filter(
            room_id=self.room_id,
            user=self.user,
        ).exists()


    @database_sync_to_async
    def is_target_in_room(
        self,
        user_id,
    ):

        return Participant.objects.filter(
            room_id=self.room_id,
            user_id=user_id,
        ).exists()
    
    @database_sync_to_async
    def is_call_active(
        self,
        call_id,
    ):

        return Call.objects.filter(
            pk=call_id,
            status__in=(
                CallStatus.RINGING,
                CallStatus.ONGOING,
            ),
        ).exists()
    
    @database_sync_to_async
    def mark_left(
        self,
    ):


        call = (
            Call.objects.filter(
                room_id=self.room_id,
                participants__user=self.user,
                status__in=(
                    CallStatus.RINGING,
                    CallStatus.ONGOING,
                ),
            )
            .distinct()
            .first()
        )

        if call:

            leave_call(
                call,
                self.user,
            )

    async def validate_call(
        self,
        data,
    ):

        call_id = data.get(
            "call_id",
        )

        if call_id is None:

            await self.send_error(
                "Call ID is required.",
            )

            return None

        active = await self.is_call_active(
            call_id,
        )

        if not active:

            await self.send_error(
                "Call is no longer active.",
            )

            return None

        return call_id


    async def receive_json(
        self,
        content,
    ):

        try:

            event = content.get("event")

            handlers = {
                "incoming_call": self.handle_incoming_call,
                "accept_call": self.handle_accept_call,
                "reject_call": self.handle_reject_call,
                "cancel_call": self.handle_cancel_call,
                "end_call": self.handle_end_call,

                "offer": self.handle_offer,
                "answer": self.handle_answer,
                "ice_candidate": self.handle_ice_candidate,

                "busy": self.handle_busy,
                "mute": self.handle_mute,
                "unmute": self.handle_unmute,

                # Video events
                "camera_on": self.handle_camera_on,
                "camera_off": self.handle_camera_off,
                "video_paused": self.handle_video_paused,
                "video_resumed": self.handle_video_resumed,
                "switch_camera": self.handle_switch_camera,
                "screen_share_started": self.handle_screen_share_started,
                "screen_share_stopped": self.handle_screen_share_stopped,

                "hold_call": self.handle_hold_call,
                "resume_call": self.handle_resume_call,
            }

            handler = handlers.get(event)

            if handler is None:

                await self.send_error(
                    "Unknown event.",
                )

                return

            await handler(content)

        except Exception as exc:

            logger.exception(exc)

            await self.send_error(
                "Something went wrong.",
            )

    

    async def handle_mute(
        self,
        data,
    ):
        
        call_id = await self.validate_call(data)

        if call_id is None:
            return

        await self.set_muted(
            call_id,
            True,
        )

        await self.relay(
            "mute",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )


    async def handle_unmute(
        self,
        data,
    ):

        call_id = await self.validate_call(data)

        if call_id is None:
            return

        await self.set_muted(
            call_id,
            False,
        )

        await self.relay(
            "unmute",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )

    async def handle_hold_call(
        self,
        data,
    ):

        call_id = await self.validate_call(
            data,
        )

        if call_id is None:
            return

        await self.set_hold(
            call_id,
            True,
        )

        await self.relay(
            "hold_call",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )


    async def handle_resume_call(
        self,
        data,
    ):

        call_id = await self.validate_call(
            data,
        )

        if call_id is None:
            return

        await self.set_hold(
            call_id,
            False,
        )

        await self.relay(
            "resume_call",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )


    async def handle_camera_on(
        self,
        data,
    ):

        call_id = await self.validate_call(data)

        if call_id is None:
            return

        await self.relay(
            "camera_on",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )

    async def handle_camera_off(
        self,
        data,
    ):

        call_id = await self.validate_call(data)

        if call_id is None:
            return

        await self.relay(
            "camera_off",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )

    async def handle_video_paused(
        self,
        data,
    ):

        call_id = await self.validate_call(data)

        if call_id is None:
            return

        await self.relay(
            "video_paused",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )


    async def handle_video_resumed(
        self,
        data,
    ):

        call_id = await self.validate_call(data)

        if call_id is None:
            return

        await self.relay(
            "video_resumed",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )

    async def handle_switch_camera(
        self,
        data,
    ):

        camera = data.get("camera")

        call_id = await self.validate_call(data)

        if call_id is None:
            return
        
        if camera not in (
            "front",
            "rear",
        ):

            await self.send_error(
                "Invalid camera.",
            )

            return

        await self.relay(
            "switch_camera",
            {
                "call_id": call_id,
                "user": self.user.id,
                "camera": camera,
            },
        )

    async def handle_screen_share_started(
        self,
        data,
    ):

        call_id = await self.validate_call(data)

        if call_id is None:
            return

        await self.relay(
            "screen_share_started",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )


    async def handle_screen_share_stopped(
        self,
        data,
    ):

        call_id = await self.validate_call(data)

        if call_id is None:
            return

        await self.relay(
            "screen_share_stopped",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )


    @database_sync_to_async
    def set_muted(
        self,
        call_id,
        muted,
    ):

        from .models import CallParticipant

        participant = CallParticipant.objects.get(
            call_id=call_id,
            user=self.user,
        )

        participant.is_muted = muted

        participant.save(
            update_fields=[
                "is_muted",
            ]
        )

    @database_sync_to_async
    def set_hold(
        self,
        call_id,
        hold,
    ):

        participant = CallParticipant.objects.get(
            call_id=call_id,
            user=self.user,
        )

        participant.is_on_hold = hold

        participant.save(
            update_fields=[
                "is_on_hold",
            ],
        )

    async def send_error(
        self,
        message,
    ):

        await self.send_json(
            {
                "event": "error",
                "message": message,
            }
        )

    async def relay(
        self,
        event,
        data,
    ):

        await self.broadcast(
            event,
            data,
        )

    async def broadcast(
        self,
        event,
        payload,
    ):

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "call.event",
                "event": event,
                "payload": payload,
            },
        )

    async def call_event(
        self,
        event,
    ):

        await self.send_json(
            {
                "event": event["event"],
                "payload": event["payload"],
            }
        )

    async def handle_incoming_call(
        self,
        data,
    ):
        
        call_id = await self.validate_call(data)

        if call_id is None:
            return
        
        logger.info(
            "User %s started call %s in room %s",
            self.user.id,
            data.get("call_id"),
            self.room_id,
        )

        call_type = data.get(
            "call_type",
        )

        if call_type not in CallType.values:

            await self.send_error(
                "Invalid call type.",
            )

            return
        

        await self.relay(
            "incoming_call",
            {
                "call_id": data["call_id"],
                "caller": self.user.id,
                "room": self.room_id,
                "call_type": call_type,
            },
        )

    async def handle_accept_call(
        self,
        data,
    ):
        
        call_id = await self.validate_call(data)

        if call_id is None:
            return

        logger.info(
            "User %s accepted call %s",
            self.user.id,
            call_id,
        )

        await self.relay(
            "accept_call",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )

    async def handle_reject_call(
        self,
        data,
    ):
        
        call_id = await self.validate_call(data)

        if call_id is None:
            return

        logger.info(
            "User %s rejected call %s",
            self.user.id,
            call_id,
        )

        await self.relay(
            "reject_call",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )

    async def handle_cancel_call(
        self,
        data,
    ):
        
        call_id = await self.validate_call(data)

        if call_id is None:
            return

        logger.info(
            "User %s cancelled call %s",
            self.user.id,
            call_id,
        )

        await self.relay(
            "cancel_call",
            {
                "call_id": call_id,
                "user": self.user.id,
            },
        )

    async def handle_end_call(
        self,
        data,
    ):
        
        call_id = await self.validate_call(data)

        if call_id is None:
            return

        logger.info(
            "User %s ended call %s",
            self.user.id,
            call_id,
        )

        call = await self.get_call(call_id)

        await self.relay(
            "call_ended",
            {
                "call_id": call.id,
                "user": self.user.id,
                "duration": call.duration,
            },
        )


    @database_sync_to_async
    def get_call(
        self,
        call_id,
    ):
        return Call.objects.get(pk=call_id)

    async def handle_offer(
        self,
        data,
    ):
        
        
        call_id = await self.validate_call(
            data,
        )

        if call_id is None:
            return

        target = data.get(
            "target",
        )

        if target is None:

            await self.send_error(
                "Target user is required.",
            )

            return

        if not data.get(
            "sdp",
        ):

            await self.send_error(
                "Missing SDP.",
            )

            return

        await self.send_to_user(
            target,
            "offer",
            data,
        )


    async def handle_answer(
        self,
        data,
    ):
        

        call_id = await self.validate_call(
            data,
        )

        if call_id is None:
            return

        target = data.get(
            "target",
        )

        if target is None:

            await self.send_error(
                "Target user is required.",
            )

            return

        if not data.get(
            "sdp",
        ):

            await self.send_error(
                "Missing SDP.",
            )

            return

        await self.send_to_user(
            target,
            "answer",
            data,
)

    async def handle_ice_candidate(
        self,
        data,
    ):


        call_id = await self.validate_call(
            data,
        )

        if call_id is None:
            return

        target = data.get(
            "target",
        )

        if target is None:

            await self.send_error(
                "Target user is required.",
            )

            return

        required = (
            "candidate",
            "sdpMid",
            "sdpMLineIndex",
        )

        for field in required:

            if not data.get(field):

                await self.send_error(
                    f"Missing {field}.",
                )
                return
            
        await self.send_to_user(
            target,
            "ice_candidate",
            data,
        )

    async def handle_busy(
        self,
        data,
    ):
        

        call_id = await self.validate_call(data)

        if call_id is None:
            return

        logger.info(
            "User %s is busy",
            self.user.id,
            call_id,

        )

        target = data.get(
            "target",
        )

        if target is None:

            await self.send_error(
                "Target user is required.",
            )

            return
        
        await self.mark_call_busy(
            call_id,
        )
        
        await database_sync_to_async(
            cancel_ring_timeout,
        )(
            call_id,
        )
        
        await self.send_to_user(
            target,
            "busy",
            {
                "call_id": call_id,
                "user": self.user.id,
                "reason": "busy",
            },
        )

    @database_sync_to_async
    def mark_call_busy(
        self,
        call_id,
    ):
        call = Call.objects.get(pk=call_id)

        call.status = CallStatus.BUSY
        call.ended_at = timezone.now()

        call.save(
            update_fields=[
                "status",
                "ended_at",
            ],
        )


    async def send_to_user(
        self,
        user_id: int,
        event: str,
        payload: dict,
    ):
        
        try:

            user_id = int(user_id)

            if user_id == self.user.id:

                await self.send_error(
                    "Cannot send signaling to yourself.",
                )

                return

        except (TypeError, ValueError):

            await self.send_error(
                "Invalid target user.",
            )

            return

        is_member = await self.is_target_in_room(
            user_id,
        )

        if not is_member:

            await self.send_error(
                "Target user is not a participant of this room.",
            )

            return

        channel = CALL_CHANNELS.get(
            user_id,
        )

        if not channel:

            await self.send_error(
                "Target user is offline.",
            )

            return

        await self.channel_layer.send(
            channel,
            {
                "type": "call.event",
                "event": event,
                "payload": payload,
            },
        )


