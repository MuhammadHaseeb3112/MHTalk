import json
from django.db.models import Q
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from apps.accounts.models import Profile

from .choices import MessageType, RoomType
from .models import ChatRoom, Message, Reaction,Attachment, VoiceNote, BlockedUser
from .serializers import MessageSerializer

 


UNAUTHORIZED = 4001
FORBIDDEN = 4003
ROOM_NOT_FOUND = 4004



class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for chat rooms.
    """

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

        await self.set_user_online()
        await self.broadcast_presence(True)


    async def disconnect(
        self,
        _close_code: int,
    ) -> None:
        """
        Remove the connection from the room group.
        """

        if hasattr(self, "room_group_name"):
            await self.set_user_offline()

            await self.broadcast_presence(False)

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

        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Invalid JSON.",
                    }
                )
            )
            return
        
        if data.get("type") == "typing":

            is_typing = bool(
                data.get("is_typing", False)
            )



            blocked = await self.is_private_chat_blocked()

            if blocked:
                return

            await self.broadcast_typing(
                is_typing,
            )

            return
        
        if data.get("type") == "delivered":

            message_id = data.get(
                "message_id",
            )

            if message_id is None:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "message_id is required.",
                        }
                    )
                )
                return

            updated = await self.mark_message_delivered(
                message_id,
            )

            if updated:
                sender_id = await self.get_message_sender_id(
                    message_id,
                )

                if sender_id is not None:
                    await self.broadcast_delivered(
                        message_id,
                        sender_id,
                    )

            return
        
        if data.get("type") == "read":

            message_id = data.get(
                "message_id",
            )

            if message_id is None:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "message_id is required.",
                        }
                    )
                )
                return

            updated = await self.mark_message_read(
                message_id,
            )

            if updated:
                sender_id = await self.get_message_sender_id(
                    message_id,
                )

                if sender_id is not None:
                    await self.broadcast_read(
                        message_id,
                        sender_id,
                    )

            return
        

        if data.get("type") == "edit":

            message_id = data.get(
                "message_id",
            )

            if message_id is None:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "message_id is required.",
                        }
                    )
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

            message_id = data.get(
                "message_id",
            )

            if message_id is None:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "message_id is required.",
                        }
                    )
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

            await self.broadcast_delete(
                message_id,
            )

            return
        
        if data.get("type") == "reaction":

            message_id = data.get(
                "message_id",
            )

            emoji = data.get(
                "emoji",
            )

            if message_id is None:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "message_id is required.",
                        }
                    )
                )
                return

            if not emoji:
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

            return
        

        if data.get("type") == "pin":

            message_id = data.get(
                "message_id",
            )

            is_pinned = data.get(
                "is_pinned",
            )

            if message_id is None:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "message_id is required.",
                        }
                    )
                )
                return

            updated = await self.pin_message(
                message_id,
                bool(is_pinned),
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
                bool(is_pinned),
            )

            return
        


        if data.get("type") == "forward":

            message_id = data.get(
                "message_id",
            )

            if message_id is None:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": "message_id is required.",
                        }
                    )
                )
                return
            

            blocked = await self.is_private_chat_blocked()

            if blocked:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": (
                                "You cannot send messages "
                                "to this user."
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

        content = data.get(
            "content",
            "",
        )

        if isinstance(content, str):
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
        
        reply_to = data.get(
            "reply_to",
        )

        if reply_to:

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
            

        blocked = await self.is_private_chat_blocked()

        if blocked:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": (
                            "You cannot send messages "
                            "to this user."
                        ),
                    }
                )
            )
            return
                    


        message = await self.save_message(
            content=content,
            message_type=message_type,
            reply_to=reply_to,
        )

        await self.broadcast_message(
            message,
        )
        

    async def chat_message(
        self,
        event,
    ):

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
        Broadcast a newly created message.
        """

        serializer = await database_sync_to_async(
            lambda: MessageSerializer(
                message,
                context={
                    "request": None,
                },
            ).data
        )()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.message",
                "message": serializer,
            },
        )

    async def presence_update(
        self,
        event: dict[str, object]
    ) -> None:
        """
        Broadcast a user's online/offline status.
        """

        await self.send(
            text_data=json.dumps(
                {
                    "type": "presence",
                    "user_id": event["user_id"],
                    "is_online": event["is_online"],
                    "last_seen": event["last_seen"],
                }
            )
        )


    async def broadcast_presence(
        self,
        is_online: bool,
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
                "last_seen": (
                    None
                    if is_online
                    else timezone.now().isoformat()
                ),
            },
        )

    async def broadcast_typing(
        self,
        is_typing: bool,
    ) -> None:
        """
        Broadcast typing status to the room.
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

    async def broadcast_delivered(
        self,
        message_id: int,
        sender_id: int,
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
            },
        )


    async def broadcast_read(
        self,
        message_id: int,
        sender_id: int,
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
            },
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
    ):

        room = ChatRoom.objects.only(
            "id",
        ).get(
            pk=self.room_id,
        )

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
        Create or update a reaction.
        """

        try:
            message = Message.objects.get(
                id=message_id,
                room_id=self.room_id,
                is_deleted=False,
            )
        except Message.DoesNotExist:
            return None

        reaction, _ = Reaction.objects.update_or_create(
            message=message,
            user=self.user,
            defaults={
                "emoji": emoji,
            },
        )

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

        updated = Message.objects.filter(
            id=message_id,
            room_id=self.room_id,
            is_deleted=False,
        ).update(
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
                .get(
                    id=message_id,
                    room_id=self.room_id,
                    is_deleted=False,
                )
            )
        except Message.DoesNotExist:
            return None

        message = Message.objects.create(
            room_id=self.room_id,
            sender=self.user,
            message_type=original.message_type,
            content=original.content,
            forwarded_from=original,
        )

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
    ) -> int:
        """
        Mark a message as delivered.
        """

        updated = Message.objects.filter(
            id=message_id,
            room_id=self.room_id,
            is_delivered=False,
            is_deleted=False,   # <-- Add this line
        ).exclude(
            sender=self.user,
        ).update(
            is_delivered=True,
            delivered_at=timezone.now(),
        )

        return updated
    
        
    
    @database_sync_to_async
    def mark_message_read(
        self,
        message_id: int,
    ) -> int:
        """
        Mark a message as read.
        """

        updated = Message.objects.filter(
            id=message_id,
            room_id=self.room_id,
            is_read=False,
            is_deleted=False,
        ).exclude(
            sender=self.user,
        ).update(
            is_read=True,
            read_at=timezone.now(),
        )

        return updated


    @database_sync_to_async
    def edit_message(
        self,
        message_id: int,
        content: str,
    ) -> int:
        """
        Edit a message.
        """

        updated = Message.objects.filter(
            id=message_id,
            room_id=self.room_id,
            sender=self.user,
            is_deleted=False,
        ).update(
            content=content,
            is_edited=True,
            updated_at=timezone.now(),
        )

        return updated
    
    @database_sync_to_async
    def delete_message(
        self,
        message_id: int,
    ) -> int:
        """
        Soft delete a message.
        """

        updated = Message.objects.filter(
            id=message_id,
            room_id=self.room_id,
            sender=self.user,
            is_deleted=False,
        ).update(
            is_deleted=True,
            is_edited=False,
            content="",
            updated_at=timezone.now(),
        )
        return updated


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
    def set_user_offline(self) -> None:
        """
        Mark the user as offline.
        """

        Profile.objects.filter(
            user_id=self.user.id,
        ).update(
            is_online=False,
            last_seen=timezone.now(),
        )

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