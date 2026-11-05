import asyncio
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .presence import clear_call_channel, get_call_channel, set_call_channel
from apps.chat.models import Participant
from .choices import CallType
from django.utils import timezone
from .lifecycle import cancel_ring_timeout

from .models import Call, CallParticipant
from .lifecycle import leave_call
from .choices import CallStatus
from django.conf import settings
from django.core.cache import cache


def _room_socket_key(room_id, user_id):
    return f"call_room_socket:{room_id}:{user_id}"


def rejoin_grace_seconds():
    """How long a 1:1 call waits for someone whose page reloaded."""
    return float(getattr(settings, "CALL_REJOIN_GRACE_SECONDS", 30))



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

        await set_call_channel(self.user.id, self.channel_name)
        await cache.aset(_room_socket_key(self.room_id, self.user.id), self.channel_name, 3600)


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

        key = _room_socket_key(self.room_id, self.user.id)
        if await cache.aget(key) == self.channel_name:
            await cache.adelete(key)

        ongoing_call_id = await self.mark_left()
        if ongoing_call_id:
            grace = rejoin_grace_seconds()
            if grace <= 0:
                await database_sync_to_async(leave_and_announce)(ongoing_call_id, self.user.id)
            else:
                schedule_task(end_after_grace(ongoing_call_id, self.user.id, self.room_id, grace))

        # A user may have multiple tabs/sockets. Do not erase a newer
        # connection's mapping when an older socket disconnects.
        await clear_call_channel(self.user.id, self.channel_name)


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

        # The call must belong to this socket's room.
        return Call.objects.filter(
            pk=call_id,
            room_id=self.room_id,
            status__in=(
                CallStatus.RINGING,
                CallStatus.ONGOING,
            ),
        ).exists()
    
    @database_sync_to_async
    def mark_left(
        self,
    ):

        # Group call: closing the call screen (or the tab) leaves the call.
        # Ringing members keep ringing across reloads.
        from .choices import ParticipantState
        from .group import leave_group_call

        group_call = (
            Call.objects.filter(
                room_id=self.room_id,
                is_group=True,
                status__in=(CallStatus.RINGING, CallStatus.ONGOING),
                participants__user=self.user,
                participants__state=ParticipantState.JOINED,
                participants__left_at__isnull=True,
            )
            .distinct()
            .first()
        )
        if group_call:
            leave_group_call(group_call, self.user)
            return

        call = (
            Call.objects.filter(
                room_id=self.room_id,
                participants__user=self.user,
                # A signaling socket can disconnect during a browser reload.
                # Keep ringing calls alive so the recipient can restore the
                # incoming-call UI; an ongoing call gets a short grace period
                # (see end_after_grace) so a reloaded page can rejoin it.
                status=CallStatus.ONGOING,
                is_group=False,
            )
            .distinct()
            .first()
        )

        return call.id if call else None

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

        # Only people who are part of the call may signal in it.
        if not await self.is_call_participant(call_id):

            await self.send_error(
                "You are not a participant of this call.",
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
                "reaction": self.handle_reaction,

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

    async def handle_reaction(
        self,
        data,
    ):
        """Emoji reaction during a call (floats up on both screens)."""

        call_id = await self.validate_call(data)

        if call_id is None:
            return

        emoji = data.get("emoji")
        if not isinstance(emoji, str) or not emoji.strip() or len(emoji) > 16:
            await self.send_error("Invalid reaction.")
            return

        await self.relay(
            "reaction",
            {
                "call_id": call_id,
                "user": self.user.id,
                "emoji": emoji.strip(),
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

    @database_sync_to_async
    def _is_call_participant(self, call_id):
        return CallParticipant.objects.filter(call_id=call_id, user_id=self.user.id).exists()

    async def is_call_participant(self, call_id):
        # Only positive answers are cached: someone added to a group after a
        # call started becomes a participant when they join it.
        cache = getattr(self, "_call_membership", None)
        if cache is None:
            cache = self._call_membership = set()
        try:
            key = int(call_id)
        except (TypeError, ValueError):
            return False
        if key in cache:
            return True
        if await self._is_call_participant(key):
            cache.add(key)
            return True
        return False

    @database_sync_to_async
    def is_group_call(self, call_id):
        return Call.objects.filter(pk=call_id, is_group=True).exists()

    @database_sync_to_async
    def can_signal(self, call_id, target_id):
        from .group import can_signal

        try:
            return can_signal(int(call_id), self.user.id, int(target_id))
        except (TypeError, ValueError):
            return False

    @database_sync_to_async
    def leave_group(self, call_id):
        from .group import leave_group_call

        call = Call.objects.filter(pk=call_id).first()
        if call is not None:
            leave_group_call(call, self.user)

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

        # Only people who are part of a call get its signaling. Someone who
        # blocked the caller is not a participant, so the call never rings
        # for them even if this conversation is open.
        payload = event.get("payload") or {}
        call_id = payload.get("call_id") if isinstance(payload, dict) else None
        if call_id and not await self.is_call_participant(call_id):
            return

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
        if await self.is_group_call(data.get("call_id")):
            # Group calls: join / decline go through the REST API (which
            # broadcasts member_* events); never end the call for everyone.
            return

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
        if await self.is_group_call(data.get("call_id")):
            # Group calls: join / decline go through the REST API (which
            # broadcasts member_* events); never end the call for everyone.
            return

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
        if await self.is_group_call(data.get("call_id")):
            # Group calls: join / decline go through the REST API (which
            # broadcasts member_* events); never end the call for everyone.
            return

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

        if await self.is_group_call(call_id):
            # "End" in a group call means leaving it.
            await self.leave_group(call_id)
            return

        call_data = await self.finish_call_record(call_id)
        if call_data is None:
            return

        await self.relay(
            "call_ended",
            {
                "call_id": call_data["id"],
                "room_id": call_data["room_id"],
                "status": call_data["status"],
                "user": self.user.id,
                "duration": call_data["duration"],
                "ended_at": call_data["ended_at"],
            },
        )


    @database_sync_to_async
    def finish_call_record(self, call_id):
        try:
            call = Call.objects.get(pk=call_id)
        except Call.DoesNotExist:
            return None
        was_active = call.status in (CallStatus.RINGING, CallStatus.ONGOING)
        if was_active:
            call.end()
        cancel_ring_timeout(call.id)
        if was_active:
            from .events import notify_calls_changed, publish_call_message

            publish_call_message(call)
            notify_calls_changed(call, "ended")
        return {
            "id": call.id,
            "room_id": call.room_id,
            "status": call.status,
            "duration": call.duration,
            "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        }


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
            pair_check=True,
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
            pair_check=True,
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

            # sdpMLineIndex=0 is valid; test for missing values rather than falsiness.
            if data.get(field) is None or data.get(field) == "":

                await self.send_error(
                    f"Missing {field}.",
                )
                return
            
        await self.send_to_user(
            target,
            "ice_candidate",
            data,
            pair_check=True,
        )

    async def handle_busy(
        self,
        data,
    ):
        if await self.is_group_call(data.get("call_id")):
            # Group calls: join / decline go through the REST API (which
            # broadcasts member_* events); never end the call for everyone.
            return


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

        from .events import notify_calls_changed, publish_call_message

        publish_call_message(call)
        notify_calls_changed(call, "busy")


    async def send_to_user(
        self,
        user_id: int,
        event: str,
        payload: dict,
        pair_check: bool = False,
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

        # Offer / answer / ICE: both people must be in this (active) call.
        if pair_check and not await self.can_signal(payload.get("call_id"), user_id):

            await self.send_error(
                "Target user is not in this call.",
            )

            return

        channel = await get_call_channel(user_id)

        if not channel:

            await self.send_error(
                "Target user is offline.",
            )

            return

        # The sender id is added by the server (never trusted from the
        # client): group calls route each signal to the right peer connection.
        relayed = {key: value for key, value in payload.items() if key not in ("event", "from")}
        relayed["from"] = self.user.id

        await self.channel_layer.send(
            channel,
            {
                "type": "call.event",
                "event": event,
                "payload": relayed,
            },
        )




class CallInboxConsumer(AsyncJsonWebsocketConsumer):
    """
    Authenticated per-user call inbox. It lets the recipient receive an
    incoming-call notification even when no conversation is currently open.
    The room-specific CallConsumer is opened after the user accepts/switches
    to the matching conversation.
    """

    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close(code=4001)
            return
        self.user_call_group = f"user_call_{self.user.id}"
        await self.channel_layer.group_add(self.user_call_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "user_call_group"):
            await self.channel_layer.group_discard(self.user_call_group, self.channel_name)

    async def call_event(self, event):
        await self.send_json({
            "event": event["event"],
            "payload": event.get("payload", {}),
        })



def leave_and_announce(call_id, user_id):
    """End a 1:1 call for someone who left and tell the other side (sync)."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from django.contrib.auth import get_user_model

    call = Call.objects.filter(pk=call_id).first()
    user = get_user_model().objects.filter(pk=user_id).first()
    if call is None or user is None or call.status != CallStatus.ONGOING:
        return False
    leave_call(call, user)
    call.refresh_from_db()
    if call.status == CallStatus.ONGOING:
        return False
    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(
            f"call_{call.room_id}",
            {"type": "call.event", "event": "call_ended", "payload": {"call_id": call.id, "status": call.status, "user": user_id}},
        )
    from .events import notify_calls_changed, publish_call_message

    try:
        publish_call_message(call)
        notify_calls_changed(call, "ended")
    except Exception:  # noqa: BLE001
        logger.exception("Couldn't announce the end of call %s", call.id)
    return True


async def end_after_grace(call_id, user_id, room_id, grace):
    """After a reload the page has `grace` seconds to reconnect to the call."""
    await asyncio.sleep(grace)
    if await cache.aget(_room_socket_key(room_id, user_id)):
        return  # back in the call
    await database_sync_to_async(leave_and_announce)(call_id, user_id)


_GRACE_TASKS = set()


def schedule_task(coro):
    task = asyncio.get_running_loop().create_task(coro)
    _GRACE_TASKS.add(task)
    task.add_done_callback(_GRACE_TASKS.discard)
