import json
from django.db.models import Q
from rest_framework.exceptions import ValidationError
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from apps.accounts.models import Profile
from apps.accounts.privacy import mask_receipt_results, presence_for_viewer, presence_snapshot_for

from .choices import MessageType, RoomType
from .models import ChatRoom, Participant, Message, Reaction, Attachment, VoiceNote, BlockedUser, MessageReceipt
from .permissions import send_message_error
from .serializers import MessageSerializer
from .utils import (
    blocked_user_ids,
    broadcast_message as broadcast_message_everywhere,
    persist_message_receipt,
    persist_receipts_bulk,
    sender_has_blocked_peer,
)

 


UNAUTHORIZED = 4001
FORBIDDEN = 4003
ROOM_NOT_FOUND = 4004



class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for chat rooms.
    """

    @staticmethod
    def parse_positive_id(value):
        """Safely parse a positive integer ID from a WebSocket payload."""
        if isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if parsed > 0 else None

    async def send_error(self, message: str) -> None:
        await self.send(text_data=json.dumps({
            "type": "error",
            "message": message,
        }))

    async def connect(self) -> None:
        """
        Authenticate the user, verify room access,
        and establish the WebSocket connection.
        """

        self.user = self.scope["user"]

        if self.user.is_anonymous:
            await self.close(
                code=UNAUTHORIZED,
            )
            return

        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]

        room_exists = await self.room_exists()

        if not room_exists:
            await self.close(
                code=ROOM_NOT_FOUND,
            )
            return

        is_participant = await self.is_participant()

        if not is_participant:
            await self.close(
                code=FORBIDDEN,
            )
            return

        self.room_group_name = f"chat_{self.room_id}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        await self.accept()

        # Online/offline is owned by ChatInboxConsumer (connection counted per
        # tab). Here we only send the joining client a presence snapshot of the
        # other participants so the chat header is correct immediately.
        for snapshot in await self.get_presence_snapshot():
            await self.send(text_data=json.dumps({"type": "presence", **snapshot}))


    async def disconnect(
        self,
        _close_code: int,
    ) -> None:
        """
        Remove the connection from the room group.
        """

        if hasattr(self, "room_group_name"):
            # Ensure a disconnect during typing cannot leave the peer stuck on
            # "typing…". App-level online presence is managed by ChatInboxConsumer.
            try:
                await self.broadcast_typing(False)
            except Exception:
                pass
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

    async def receive(
        self,
        text_data: str,
    ) -> None:
        """
        Receive a message from the client.
        """

        try:
            data = json.loads(text_data)

        except (json.JSONDecodeError, TypeError):
            await self.send_error("Invalid JSON.")
            return

        if not isinstance(data, dict):
            await self.send_error("WebSocket payload must be a JSON object.")
            return

        if data.get("type") == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
            return

        if data.get("type") == "typing":

            is_typing_value = data.get("is_typing", False)
            if not isinstance(is_typing_value, bool):
                await self.send_error("is_typing must be a boolean.")
                return
            is_typing = is_typing_value



            blocked = await self.is_private_chat_blocked()

            if blocked:
                return

            await self.broadcast_typing(
                is_typing,
            )

            return
        
        if data.get("type") == "delivered":

            message_id = self.parse_positive_id(data.get("message_id"))

            if message_id is None:
                await self.send_error(
                    "A valid positive message_id is required."
                )
                return

            updated = await self.mark_message_delivered(message_id)
            if updated:
                await self.broadcast_delivered(message_id, updated["sender_id"], updated)

            return
        
        if data.get("type") == "read":

            message_id = self.parse_positive_id(data.get("message_id"))

            if message_id is None:
                await self.send_error(
                    "A valid positive message_id is required."
                )
                return

            updated = await self.mark_message_read(message_id)
            if updated and updated.get("receipt") == "delivered":
                await self.broadcast_delivered(message_id, updated["sender_id"], updated)
            elif updated:
                await self.broadcast_read(message_id, updated["sender_id"], updated)

            return
        

        if data.get("type") == "edit":

            message_id = self.parse_positive_id(data.get("message_id"))

            if message_id is None:
                await self.send_error(
                    "A valid positive message_id is required."
                )
                return
            
            content = data.get(
                "content",
                "",
            )

            if isinstance(content, str):
                content = content.strip()

            if not content:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "Message cannot be empty.",
                        }
                    )
                )
                return

            updated = await self.edit_message(
                message_id,
                content,
            )


            if not updated:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "You cannot edit this message.",
                        }
                    )
                )
                return

            await self.broadcast_edit(
                message_id,
                content,
            )

            return


        if data.get("type") == "delete":

            message_id = self.parse_positive_id(data.get("message_id"))

            if message_id is None:
                await self.send_error(
                    "A valid positive message_id is required."
                )
                return

            updated = await self.delete_message(
                message_id,
            )

            if not updated:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "You cannot delete this message.",
                        }
                    )
                )
                return

            # soft_delete_messages_for_everyone already broadcast the deletion.

            return
        
        if data.get("type") == "reaction":

            message_id = self.parse_positive_id(data.get("message_id"))

            emoji = data.get(
                "emoji",
            )

            if message_id is None:
                await self.send_error(
                    "A valid positive message_id is required."
                )
                return

            if not isinstance(emoji, str) or len(emoji) > 20:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "emoji is required.",
                        }
                    )
                )
                return

            reaction = await self.save_reaction(
                message_id,
                emoji,
            )

            if reaction is None:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "Cannot react to this message.",
                        }
                    )
                )
                return

            await self.broadcast_reaction(
                message_id,
                emoji,
            )
            await self.announce_room_activity("reaction")

            return
        

        if data.get("type") == "pin":

            message_id = self.parse_positive_id(data.get("message_id"))

            is_pinned = data.get(
                "is_pinned",
            )

            if message_id is None:
                await self.send_error(
                    "A valid positive message_id is required."
                )
                return

            if not isinstance(is_pinned, bool):
                await self.send_error("is_pinned must be a boolean.")
                return

            updated = await self.pin_message(
                message_id,
                is_pinned,
            )

            if not updated:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "Cannot pin this message.",
                        }
                    )
                )
                return

            await self.broadcast_pin(
                message_id,
                is_pinned,
            )

            return
        


        if data.get("type") == "forward":

            message_id = self.parse_positive_id(data.get("message_id"))

            if message_id is None:
                await self.send_error(
                    "A valid positive message_id is required."
                )
                return
            

            denied = await self.send_denied_reason()
            if denied:
                await self.send_error(denied)
                return

            blocked = await self.sender_blocked_peer()

            if blocked:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": (
                                "Unblock this contact to send a message."
                            ),
                        }
                    )
                )
                return

            message = await self.forward_message(
                message_id,
            )

            if message is None:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "Cannot forward this message.",
                        }
                    )
                )
                return

            await self.broadcast_message(
                message,
            )

            return

        # Only an explicit (or legacy untyped) "send" creates a message; any
        # other control frame we don't know is ignored instead of turning
        # into an empty-message error.
        if data.get("type") not in (None, "", "message", "chat_message", "send"):
            return

        message_type = data.get(
            "message_type",
            MessageType.TEXT,
        )

        if message_type not in MessageType.values:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Invalid message type.",
                    }
                )
            )
            return

        if message_type in (MessageType.POLL, MessageType.LOCATION):
            # They need structured validation: use POST /api/chat/messages/.
            await self.send_error("Send polls and locations through the REST API.")
            return

        content = data.get(
            "content",
            "",
        )

        if not isinstance(content, str):
            await self.send_error("content must be a string.")
            return

        content = content.strip()

        if (
            message_type == MessageType.TEXT
            and not content
        ):
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Message cannot be empty.",
                    }
                )
            )
            return
        
        reply_to_raw = data.get("reply_to")
        reply_to = None

        if reply_to_raw not in (None, ""):
            reply_to = self.parse_positive_id(reply_to_raw)
            if reply_to is None:
                await self.send_error("reply_to must be a valid positive message ID.")
                return

            exists = await self.reply_message_exists(
                reply_to,
            )

            if not exists:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "Invalid reply message.",
                        }
                    )
                )
                return
            

        denied = await self.send_denied_reason()
        if denied:
            await self.send_error(denied)
            return

        blocked = await self.sender_blocked_peer()

        if blocked:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": (
                            "Unblock this contact to send a message."
                        ),
                    }
                )
            )
            return

        try:
            message = await self.save_message(
                content=content,
                message_type=message_type,
                reply_to=reply_to,
                mentions=data.get("mentions"),
            )
        except ValidationError as error:
            detail = error.detail
            if isinstance(detail, dict):
                detail = next(iter(detail.values()), "Invalid message.")
            if isinstance(detail, list):
                detail = detail[0] if detail else "Invalid message."
            await self.send_error(str(detail))
            return

        await self.broadcast_message(
            message,
        )
        

    async def chat_message(
        self,
        event,
    ):

        if self.user.id in (event.get("hidden_for") or ()):
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "message",
                    "message": event["message"],
                }
            )
        )


    async def broadcast_message(
    self,
    message,
    ):
        """
        Broadcast a newly created message (same path as the REST views, so
        block rules, receipts and inbox updates are identical).
        """

        await database_sync_to_async(broadcast_message_everywhere)(message)

    @database_sync_to_async
    def get_presence_snapshot(self):
        profiles = (
            Profile.objects.filter(
                user__chat_participations__room_id=self.room_id,
                user__is_deleted=False,
            )
            .exclude(user_id=self.user.id)
            .exclude(user_id__in=blocked_user_ids(self.user.id))
        )
        viewer = type(self.user).objects.select_related("profile").get(pk=self.user.id)
        # Privacy settings (last seen / online, with reciprocity) per viewer.
        return presence_snapshot_for(viewer, [
            {
                "user_id": profile.user_id,
                "profile": profile,
                "is_online": bool(profile.is_online),
                "last_seen": None if profile.is_online or not profile.last_seen else profile.last_seen.isoformat(),
            }
            for profile in profiles
        ])

    @database_sync_to_async
    def get_other_participant_ids(self):
        return list(Participant.objects.filter(room_id=self.room_id)
                    .exclude(user_id=self.user.id).values_list("user_id", flat=True))

    async def presence_update(
        self,
        event: dict[str, object]
    ) -> None:
        """
        Broadcast a user's online/offline status.
        """

        if event.get("user_id") in await self.blocked_ids():
            return
        is_online, last_seen = await database_sync_to_async(presence_for_viewer)(
            event["user_id"], self.user.id, bool(event.get("is_online")), event.get("last_seen"),
        )

        await self.send(
            text_data=json.dumps(
                {
                    "type": "presence",
                    "user_id": event["user_id"],
                    "is_online": is_online,
                    "last_seen": last_seen,
                }
            )
        )


    async def broadcast_presence(
        self,
        is_online: bool,
        last_seen: str | None = None,
    ) -> None:
        """
        Broadcast the user's online/offline status
        to everyone in the room.
        """

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "presence.update",
                "user_id": self.user.id,
                "is_online": is_online,
                "last_seen": None if is_online else (last_seen or timezone.now().isoformat()),
            },
        )

    async def broadcast_typing(
        self,
        is_typing: bool,
    ) -> None:
        """
        Broadcast typing status to the room and to the other participants'
        inboxes, so "typing…" also appears in their chat lists.
        """

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "typing.update",
                "user_id": self.user.id,
                "sender_phone": self.user.phone_number,
                "is_typing": is_typing,
            },
        )
        for recipient_id in await self.get_other_participant_ids():
            await self.channel_layer.group_send(
                f"chat_inbox_{recipient_id}",
                {
                    "type": "inbox.typing",
                    "room_id": int(self.room_id),
                    "user_id": self.user.id,
                    "is_typing": is_typing,
                },
            )

    async def broadcast_delivered(
        self,
        message_id: int,
        sender_id: int,
        receipt_state: dict | None = None,
    ) -> None:
        """
        Broadcast that a message has been delivered.
        """

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "message.delivered",
                "message_id": message_id,
                "sender_id": sender_id,
                "is_delivered": bool((receipt_state or {}).get("is_delivered", True)),
                "is_read": bool((receipt_state or {}).get("is_read", False)),
            },
        )
        await self.channel_layer.group_send(
            f"chat_inbox_{sender_id}",
            {"type": "inbox.receipt", "room_id": int(self.room_id), "message_id": message_id, "receipt": "delivered",
             "is_delivered": bool((receipt_state or {}).get("is_delivered", True)),
             "is_read": bool((receipt_state or {}).get("is_read", False))},
        )


    async def broadcast_read(
        self,
        message_id: int,
        sender_id: int,
        receipt_state: dict | None = None,
    ) -> None:
        """
        Broadcast that a message has been read.
        """

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "message.read",
                "message_id": message_id,
                "sender_id": sender_id,
                "is_delivered": bool((receipt_state or {}).get("is_delivered", True)),
                "is_read": bool((receipt_state or {}).get("is_read", True)),
            },
        )
        await self.channel_layer.group_send(
            f"chat_inbox_{sender_id}",
            {"type": "inbox.receipt", "room_id": int(self.room_id), "message_id": message_id, "receipt": "read",
             "is_delivered": bool((receipt_state or {}).get("is_delivered", True)),
             "is_read": bool((receipt_state or {}).get("is_read", True))},
        )


    async def broadcast_edit(
        self,
        message_id: int,
        content: str,
    ) -> None:
        """
        Broadcast that a message
        has been edited.
        """

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "message.edited",
                "message_id": message_id,
                "content": content,
                "is_edited": True,
            },
        )


    async def broadcast_delete(
        self,
        message_id: int,
    ) -> None:
        """
        Broadcast that a message
        has been deleted.
        """

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "message.deleted",
                "message_id": message_id,
            },
        )

    async def announce_room_activity(self, action):
        """Tell every member's inbox to refresh this chat in their list."""
        user_ids = await database_sync_to_async(
            lambda: list(Participant.objects.filter(room_id=self.room_id).values_list("user_id", flat=True))
        )()
        for user_id in user_ids:
            await self.channel_layer.group_send(
                f"chat_inbox_{user_id}",
                {"type": "inbox.room_changed", "room_id": int(self.room_id), "action": action},
            )

    async def broadcast_reaction(
        self,
        message_id: int,
        emoji: str,
    ) -> None:
        """
        Broadcast a message reaction.
        """

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "message.reaction",
                "message_id": message_id,
                "user_id": self.user.id,
                "sender_phone": self.user.phone_number,
                "emoji": emoji,
            },
        )



    async def broadcast_pin(
        self,
        message_id: int,
        is_pinned: bool,
    ) -> None:
        """
        Broadcast message pin/unpin.
        """

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "message.pinned",
                "message_id": message_id,
                "is_pinned": is_pinned,
            },
        )

    async def typing_update(
        self,
        event: dict,
    ) -> None:
        """
        Send typing status to other connected clients.
        """

        if event["user_id"] == self.user.id:
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "typing",
                    "user_id": event["user_id"],
                    "sender_phone": event["sender_phone"],
                    "is_typing": event["is_typing"],
                }
            )
        )


    async def message_delivered(
        self,
        event: dict,
    ) -> None:
        """
        Notify clients that a message
        has been delivered.
        """


        if event["sender_id"] != self.user.id:
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "delivered",
                    "message_id": event["message_id"],
                    "is_delivered": bool(event.get("is_delivered", True)),
                    "is_read": bool(event.get("is_read", False)),
                }
            )
        )


    async def message_read(
        self,
        event: dict,
    ) -> None:
        """
        Notify the sender that
        the message has been read.
        """

        if event["sender_id"] != self.user.id:
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "read",
                    "message_id": event["message_id"],
                    "is_delivered": bool(event.get("is_delivered", True)),
                    "is_read": bool(event.get("is_read", True)),
                }
            )
        )


    async def message_edited(
        self,
        event: dict,
    ) -> None:
        """
        Notify all clients that
        a message has been edited.
        """

        await self.send(
            text_data=json.dumps(
                {
                    "type": "edited",
                    "message_id": event["message_id"],
                    "content": event["content"],
                    "is_edited": event["is_edited"],
                }
            )
        )

    
    async def message_deleted(
        self,
        event: dict,
    ) -> None:
        """
        Notify all clients that
        a message has been deleted.
        """

        await self.send(
            text_data=json.dumps(
                {
                    "type": "deleted",
                    "message_id": event["message_id"],
                }
            )
        )


    async def message_reaction(
        self,
        event: dict,
    ) -> None:
        """
        Notify all clients that
        a reaction was added or updated.
        """

        await self.send(
            text_data=json.dumps(
                {
                    "type": "reaction",
                    "message_id": event["message_id"],
                    "user_id": event["user_id"],
                    "sender_phone": event["sender_phone"],
                    "emoji": event["emoji"],
                }
            )
        )

    
    async def message_patch(self, event: dict) -> None:
        """Partial message update (poll votes, view once opened...)."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "patch",
                    "message_id": event["message_id"],
                    "patch": event["patch"],
                }
            )
        )

    async def message_pinned(
        self,
        event: dict,
    ) -> None:
        """
        Notify clients that a message
        was pinned or unpinned.
        """

        await self.send(
            text_data=json.dumps(
                {
                    "type": "pin",
                    "message_id": event["message_id"],
                    "is_pinned": event["is_pinned"],
                }
            )
        )


    @database_sync_to_async
    def save_message(
        self,
        content,
        message_type,
        reply_to,
        mentions=None,
    ):
        from .features import save_mentions, validate_mentions
        from .link_preview import extract_first_url, get_link_preview

        room = ChatRoom.objects.only(
            "id",
            "room_type",
        ).get(
            pk=self.room_id,
        )
        mention_ids = validate_mentions(room, mentions)

        reply_message = None

        if reply_to:
            reply_message = Message.objects.filter(
                id=reply_to,
                room=room,
                is_deleted=False,
            ).first()

        message = Message.objects.create(
            room=room,
            sender=self.user,
            content=content,
            message_type=message_type,
            reply_to=reply_message,
            # Only a cached preview here: never block the socket on the network.
            link_preview=(
                get_link_preview(extract_first_url(content), use_network=False)
                if message_type == MessageType.TEXT
                else None
            ),
        )
        save_mentions(message, mention_ids)

        return (
            Message.objects
            .select_related(
                "sender",
                "sender__profile",
                "reply_to",
                "reply_to__sender",
                "reply_to__sender__profile",
                "forwarded_from",
                "forwarded_from__sender",
                "forwarded_from__sender__profile",
            )
            .prefetch_related(
                "attachments",
                "reactions",
                "voice_note",
            )
            .get(
                pk=message.pk,
            )
        )
                
    @database_sync_to_async
    def reply_message_exists(
        self,
        reply_to: int,
    ) -> bool:
        """
        Return True if the reply message exists
        in the current room and is not deleted.
        """

        return Message.objects.filter(
            id=reply_to,
            room_id=self.room_id,
            is_deleted=False,
        ).exists()
    

    @database_sync_to_async
    def save_reaction(
        self,
        message_id: int,
        emoji: str,
    ):
        """
        Create, update or (with an empty emoji) remove a reaction.
        """

        try:
            message = Message.objects.get(
                id=message_id,
                room_id=self.room_id,
                is_deleted=False,
            )
        except Message.DoesNotExist:
            return None

        if not emoji:
            Reaction.objects.filter(message=message, user=self.user).delete()
            return True

        reaction, _ = Reaction.objects.update_or_create(
            message=message,
            user=self.user,
            defaults={
                "emoji": emoji,
                # A changed reaction is the newest activity again (chat list).
                "created_at": timezone.now(),
            },
        )
        ChatRoom.objects.filter(pk=message.room_id).update(updated_at=timezone.now())

        return reaction

    @database_sync_to_async
    def pin_message(
        self,
        message_id: int,
        is_pinned: bool,
    ) -> int:
        """
        Pin or unpin a message.
        """

        from .group_events import GROUP_EVENT_PREFIX

        updated = Message.objects.filter(
            id=message_id,
            room_id=self.room_id,
            is_deleted=False,
        ).exclude(content__startswith=GROUP_EVENT_PREFIX).update(
            is_pinned=is_pinned,
            pinned_at=(
                timezone.now()
                if is_pinned
                else None
            ),
        )

        return updated
    

    @database_sync_to_async
    def forward_message(
        self,
        message_id: int,
    ):
        """
        Forward an existing message.
        """
        from .group_events import GROUP_EVENT_PREFIX

        try:
            original = (
                Message.objects
                .select_related(
                    "sender",
                    "sender__profile",
                    "reply_to",
                    "reply_to__sender",
                    "reply_to__sender__profile",
                    "forwarded_from",
                    "forwarded_from__sender",
                    "forwarded_from__sender__profile",
                )
                .prefetch_related(
                    "attachments",
                    "reactions",
                     "voice_note",
                )
                .exclude(content__startswith=GROUP_EVENT_PREFIX)
                .get(
                    id=message_id,
                    room_id=self.room_id,
                    is_deleted=False,
                )
            )
        except Message.DoesNotExist:
            return None

        if original.is_view_once or original.is_system:
            return None

        message = Message.objects.create(
            room_id=self.room_id,
            sender=self.user,
            message_type=original.message_type,
            content=original.content,
            link_preview=original.link_preview,
            forwarded_from=original,
        )

        from .features import copy_poll

        copy_poll(original, message)

        # Copy attachments
        for attachment in original.attachments.all():

            Attachment.objects.create(
                message=message,
                file=attachment.file,
            )

        if hasattr(original, "voice_note"):

            VoiceNote.objects.create(
                message=message,
                audio=original.voice_note.audio,
                duration=original.voice_note.duration,
                waveform=list(original.voice_note.waveform),
            )

        return (
            Message.objects
            .select_related(
                "sender",
                "sender__profile",
                "reply_to",
                "reply_to__sender",
                "reply_to__sender__profile",
                "forwarded_from",
                "forwarded_from__sender",
                "forwarded_from__sender__profile",
            )
            .prefetch_related(
                "attachments",
                "reactions",
                "voice_note",

            )
            .get(
                pk=message.pk,
            )
        )
    

    @database_sync_to_async
    def mark_message_delivered(
        self,
        message_id: int,
    ) -> dict | None:
        """
        Mark a message as delivered.
        """

        message = Message.objects.filter(pk=message_id, room_id=self.room_id, is_deleted=False).first()
        if message is None or message.sender_id == self.user.id:
            return None
        result = persist_message_receipt(message_id, self.user.id, "delivered")
        if result:
            result["sender_id"] = message.sender_id
        return result
    
        
    
    @database_sync_to_async
    def mark_message_read(
        self,
        message_id: int,
    ) -> dict | None:
        """Mark an incoming message read; read necessarily implies delivery."""
        message = Message.objects.filter(pk=message_id, room_id=self.room_id, is_deleted=False).first()
        if message is None or message.sender_id == self.user.id:
            return None
        result = persist_message_receipt(message_id, self.user.id, "read")
        if result:
            result = mask_receipt_results([result])[0]
            result["sender_id"] = message.sender_id
        return result



    @database_sync_to_async
    def edit_message(
        self,
        message_id: int,
        content: str,
    ) -> int:
        """
        Edit a text message within the edit window.
        """
        from .views import edit_window_open

        message = Message.objects.filter(
            id=message_id,
            room_id=self.room_id,
            sender=self.user,
            is_deleted=False,
            message_type=MessageType.TEXT,
        ).first()
        if message is None or str(message.content or "").startswith("__MHTALK_"):
            return 0
        if not edit_window_open(message):
            return 0

        return Message.objects.filter(pk=message.pk).update(
            content=content,
            is_edited=True,
            updated_at=timezone.now(),
        )

    @database_sync_to_async
    def delete_message(
        self,
        message_id: int,
    ) -> int:
        """
        Delete a message for everyone (sender only, within the time window).
        Media, reactions and stars are removed; a tombstone is kept.
        """
        from .views import delete_for_everyone_window_open
        from .utils import soft_delete_messages_for_everyone

        from .group_events import GROUP_EVENT_PREFIX

        message = Message.objects.filter(
            id=message_id,
            room_id=self.room_id,
            sender=self.user,
            is_deleted=False,
        ).exclude(content__startswith=GROUP_EVENT_PREFIX).first()
        if message is None or not delete_for_everyone_window_open(message):
            return 0
        # soft_delete_messages_for_everyone broadcasts the deletion itself.
        return len(soft_delete_messages_for_everyone([message]))

    @database_sync_to_async
    def get_message_sender_id(
        self,
        message_id: int,
    ) -> int | None:
        """
        Return the sender ID for a message.
        """

        return (
            Message.objects.filter(
                id=message_id,
                room_id=self.room_id,
            )
            .values_list("sender_id", flat=True)
            .first()
        )

    @database_sync_to_async
    def set_user_online(self) -> None:
        """
        Mark the user as online.
        """

        Profile.objects.filter(
            user_id=self.user.id,
        ).update(
            is_online=True,
        )


    @database_sync_to_async
    def set_user_offline(self):
        """Persist offline status and return the saved last-seen timestamp."""
        last_seen = timezone.now()
        Profile.objects.filter(user_id=self.user.id).update(
            is_online=False,
            last_seen=last_seen,
        )
        return last_seen.isoformat()

    @database_sync_to_async
    def send_denied_reason(self):
        """Group "only admins can send", deleted peer, … (None when allowed)."""
        return send_message_error(self.user, self.room_id)

    @database_sync_to_async
    def sender_blocked_peer(self):
        room = ChatRoom.objects.filter(pk=self.room_id).first()
        return bool(room) and sender_has_blocked_peer(room, self.user)

    @database_sync_to_async
    def blocked_ids(self):
        return blocked_user_ids(self.user.id)

    @database_sync_to_async
    def is_private_chat_blocked(
        self,
    ) -> bool:
        """
        Return True if either participant
        has blocked the other.
        """

        room = ChatRoom.objects.get(
            pk=self.room_id,
        )

        if room.room_type != RoomType.PRIVATE:
            return False

        other = (
            room.participants
            .exclude(user=self.user)
            .select_related("user")
            .first()
        )

        if not other:
            return False

        return BlockedUser.objects.filter(
            Q(
                blocked_by=self.user,
                blocked_user=other.user,
            )
            |
            Q(
                blocked_by=other.user,
                blocked_user=self.user,
            )
        ).exists()

    @database_sync_to_async
    def room_exists(self) -> bool:
        """
        Return True if the room exists.
        """

        return ChatRoom.objects.filter(
            pk=self.room_id,
            is_active=True,
        ).exists()

    @database_sync_to_async
    def is_participant(self) -> bool:
        """
        Return True if the authenticated user
        belongs to this room.
        """

        return ChatRoom.objects.filter(
            pk=self.room_id,
            participants__user=self.user,
            is_active=True,
        ).exists()

    

class ChatInboxConsumer(AsyncWebsocketConsumer):
    """
    Per-user inbox socket (one per open tab/device).

    Delivers new messages, receipts, typing and presence for every chat so
    the sidebar stays live, plus nudges (room/contacts/profile/status/call
    changes) that tell the client to re-sync that slice over REST. It also
    owns the user's online state: the profile counts live connections and is
    only marked offline when the last tab disconnects.
    """

    @staticmethod
    def parse_positive_id(value):
        if isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if parsed > 0 else None

    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close(code=UNAUTHORIZED)
            return
        self.inbox_group_name = f"chat_inbox_{self.user.id}"
        await self.channel_layer.group_add(self.inbox_group_name, self.channel_name)
        await self.accept()
        became_online = await self.register_connection()
        if became_online:
            await self.broadcast_presence(True)
        # Messages that arrived while this user was offline are now on a
        # device: mark them delivered (grey double tick) for their senders.
        await self.deliver_pending_messages()

    async def disconnect(self, close_code):
        if not hasattr(self, "inbox_group_name"):
            return
        await self.channel_layer.group_discard(self.inbox_group_name, self.channel_name)
        last_seen = await self.unregister_connection()
        if last_seen:
            await self.broadcast_presence(False, last_seen=last_seen)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(data, dict):
            return
        if data.get("type") == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
            return
        if data.get("type") not in {"delivered", "read"}:
            return
        message_id = self.parse_positive_id(data.get("message_id"))
        room_id = self.parse_positive_id(data.get("room_id"))
        if not message_id or not room_id:
            return
        receipt = "read" if data.get("type") == "read" else "delivered"
        message_info = await self.record_receipt(message_id, room_id, receipt)
        if not message_info:
            return
        sender_id = message_info["sender_id"]
        receipt = message_info.get("receipt", receipt)
        handler_type = "message.read" if receipt == "read" else "message.delivered"
        await self.channel_layer.group_send(
            f"chat_{room_id}",
            {"type": handler_type, "message_id": message_id, "sender_id": sender_id,
             "is_delivered": message_info["is_delivered"], "is_read": message_info["is_read"]},
        )
        await self.channel_layer.group_send(
            f"chat_inbox_{sender_id}",
            {"type": "inbox.receipt", "room_id": room_id, "message_id": message_id, "receipt": receipt,
             "is_delivered": message_info["is_delivered"], "is_read": message_info["is_read"]},
        )

    # -- events pushed to the client ----------------------------------------
    async def inbox_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "inbox.message",
            "room_id": event["room_id"],
            "message": event["message"],
        }))

    async def inbox_message_patch(self, event):
        await self.send(text_data=json.dumps({
            "type": "message.patch",
            "room_id": event["room_id"],
            "message_id": event["message_id"],
            "patch": event["patch"],
        }))

    async def inbox_room_changed(self, event):
        await self.send(text_data=json.dumps({
            "type": "room.updated",
            "room_id": event.get("room_id"),
            "action": event.get("action", "updated"),
        }))

    async def inbox_receipt(self, event):
        await self.send(text_data=json.dumps({
            "type": "receipt",
            "room_id": event["room_id"],
            "message_id": event["message_id"],
            "receipt": event["receipt"],
            "is_delivered": bool(event.get("is_delivered", True)),
            "is_read": bool(event.get("is_read", False)),
        }))

    async def inbox_typing(self, event):
        if event.get("user_id") == self.user.id:
            return
        await self.send(text_data=json.dumps({
            "type": "typing",
            "room_id": event["room_id"],
            "user_id": event["user_id"],
            "is_typing": bool(event.get("is_typing")),
        }))

    async def inbox_presence(self, event):
        # Blocked (either way): never reveal online / last seen.
        if event.get("user_id") in await database_sync_to_async(blocked_user_ids)(self.user.id):
            return
        # Last seen & online privacy (with reciprocity) for this viewer.
        is_online, last_seen = await database_sync_to_async(presence_for_viewer)(
            event["user_id"], self.user.id, bool(event.get("is_online")), event.get("last_seen"),
        )
        await self.send(text_data=json.dumps({
            "type": "presence",
            "user_id": event["user_id"],
            "is_online": is_online,
            "last_seen": last_seen,
        }))

    async def inbox_account_deleted(self, event):
        # The account was deleted (possibly from another tab): sign out.
        await self.send(text_data=json.dumps({"type": "account.deleted"}))
        await self.close(code=UNAUTHORIZED)

    async def inbox_profile_changed(self, event):
        await self.send(text_data=json.dumps({"type": "profile.updated", "user_id": event.get("user_id")}))

    async def inbox_contacts_changed(self, event):
        await self.send(text_data=json.dumps({"type": "contacts.updated"}))

    async def inbox_status_changed(self, event):
        payload = {key: value for key, value in event.items() if key != "type"}
        await self.send(text_data=json.dumps({"type": "status.updated", **payload}))

    async def inbox_call_changed(self, event):
        payload = {key: value for key, value in event.items() if key != "type"}
        await self.send(text_data=json.dumps({"type": "calls.updated", **payload}))

    # Room-level presence events may also be routed here; reuse the handler.
    async def presence_update(self, event):
        await self.inbox_presence(event)

    # -- database helpers ---------------------------------------------------
    @database_sync_to_async
    def record_receipt(self, message_id, room_id, receipt):
        message = Message.objects.filter(
            pk=message_id,
            room_id=room_id,
            room__participants__user_id=self.user.id,
            is_deleted=False,
        ).exclude(sender_id=self.user.id).first()
        if message is None:
            return None
        if not Participant.objects.filter(room_id=room_id, user_id=self.user.id).exists():
            return None
        result = persist_message_receipt(message_id, self.user.id, receipt)
        if not result:
            return None
        # Read receipts off in this private chat: the sender only sees grey ticks.
        result = mask_receipt_results([result])[0]
        return {"sender_id": message.sender_id, "room_id": room_id, "receipt": result["receipt"],
                "is_delivered": result["is_delivered"], "is_read": result["is_read"]}

    @database_sync_to_async
    def deliver_pending_messages(self):
        from .utils import broadcast_receipts

        pending_ids = list(
            MessageReceipt.objects.filter(
                recipient_id=self.user.id,
                delivered_at__isnull=True,
                message__is_deleted=False,
            ).exclude(message__deleted_for_users__user_id=self.user.id)
            .values_list("message_id", flat=True)[:500]
        )
        results = persist_receipts_bulk(pending_ids, self.user.id, "delivered")
        broadcast_receipts(results)
        return len(results)

    @database_sync_to_async
    def register_connection(self):
        """Count this tab; return True when the user just came online."""
        from django.db.models import F

        Profile.objects.filter(user_id=self.user.id).update(
            active_connections=F("active_connections") + 1,
            is_online=True,
        )
        count = Profile.objects.filter(user_id=self.user.id).values_list("active_connections", flat=True).first()
        return count == 1

    @database_sync_to_async
    def unregister_connection(self):
        """Uncount this tab; return the last-seen ISO time if the user went offline."""
        from django.db import transaction
        from django.db.models import F
        from django.db.models.functions import Greatest

        with transaction.atomic():
            Profile.objects.filter(user_id=self.user.id).update(
                active_connections=Greatest(F("active_connections") - 1, 0),
            )
            remaining = Profile.objects.filter(user_id=self.user.id).values_list(
                "active_connections", flat=True
            ).first()
            if remaining:
                return None
            last_seen = timezone.now()
            Profile.objects.filter(user_id=self.user.id, active_connections=0).update(
                is_online=False,
                last_seen=last_seen,
            )
        return last_seen.isoformat()

    @database_sync_to_async
    def get_contact_user_ids(self):
        room_ids = Participant.objects.filter(user_id=self.user.id).values_list("room_id", flat=True)
        return list(
            Participant.objects.filter(room_id__in=room_ids)
            .exclude(user_id=self.user.id)
            .values_list("user_id", flat=True)
            .distinct()
        )

    @database_sync_to_async
    def get_participating_room_ids(self):
        return list(Participant.objects.filter(user_id=self.user.id).values_list("room_id", flat=True))

    async def broadcast_presence(self, is_online, last_seen=None):
        payload = {
            "type": "presence.update",
            "user_id": self.user.id,
            "is_online": is_online,
            "last_seen": None if is_online else (last_seen or timezone.now().isoformat()),
        }
        # Open conversations (room sockets) and every contact's chat list.
        for room_id in await self.get_participating_room_ids():
            await self.channel_layer.group_send(f"chat_{room_id}", payload)
        inbox_payload = {**payload, "type": "inbox.presence"}
        for user_id in await self.get_contact_user_ids():
            await self.channel_layer.group_send(f"chat_inbox_{user_id}", inbox_payload)
