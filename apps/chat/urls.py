from django.urls import path

from .views import (
    AddParticipantAPIView,
    ChatRoomDetailAPIView,
    ChatRoomListAPIView,
    CreateGroupChatAPIView,
    CreatePrivateChatAPIView,
    DeleteMessageAPIView,
    LeaveGroupAPIView,
    MessageListAPIView,
    RemoveParticipantAPIView,
    SendMessageAPIView,
    UploadMessageAPIView,
    UpdateMessageAPIView,
    ReactMessageAPIView,
    PinMessageAPIView,
    SearchMessagesAPIView,
    StarMessageAPIView,
    StarredMessagesAPIView,
    ForwardMessageAPIView,
    BlockedUsersAPIView,
    UnblockUserAPIView,
    BlockUserAPIView,
    MuteChatAPIView,
    ArchiveChatAPIView,
    DeleteForMeAPIView,
    UploadVoiceAPIView,

)

app_name = "chat"

urlpatterns = [
    # ==========================
    # Chat Rooms
    # ==========================
    path(
        "rooms/",
        ChatRoomListAPIView.as_view(),
        name="room-list",
    ),
    path(
        "rooms/private/",
        CreatePrivateChatAPIView.as_view(),
        name="private-room-create",
    ),
    path(
        "rooms/group/",
        CreateGroupChatAPIView.as_view(),
        name="group-room-create",
    ),
    path(
        "rooms/<int:pk>/",
        ChatRoomDetailAPIView.as_view(),
        name="room-detail",
    ),

    # ==========================
    # Messages
    # ==========================
    path(
        "rooms/<int:room_id>/messages/",
        MessageListAPIView.as_view(),
        name="message-list",
    ),
    path(
        "messages/",
        SendMessageAPIView.as_view(),
        name="message-create",
    ),

    path(
        "messages/upload/",
        UploadMessageAPIView.as_view(),
        name="message-upload",
    ),

    path(
        "messages/voice/",
        UploadVoiceAPIView.as_view(),
        name="voice-upload",
    ),

    path(
        "messages/react/",
        ReactMessageAPIView.as_view(),
        name="message-react",
    ),

    path(
        "messages/pin/",
        PinMessageAPIView.as_view(),
        name="message-pin",
    ),

    path(
        "messages/star/",
        StarMessageAPIView.as_view(),
        name="message-star",
    ),

    path(
        "messages/starred/",
        StarredMessagesAPIView.as_view(),
        name="starred-messages",
    ),

    path(
        "messages/forward/",
        ForwardMessageAPIView.as_view(),
        name="message-forward",
    ),

    path(
        "rooms/mute/",
        MuteChatAPIView.as_view(),
        name="chat-mute",
    ),

    path(
        "rooms/archive/",
        ArchiveChatAPIView.as_view(),
        name="archive-chat",
    ),

    path(
        "users/block/",
        BlockUserAPIView.as_view(),
        name="block-user",
    ),

    path(
        "users/unblock/",
        UnblockUserAPIView.as_view(),
        name="unblock-user",
    ),

    path(
        "users/blocked/",
        BlockedUsersAPIView.as_view(),
        name="blocked-users",
    ),


    path(
        "messages/<int:pk>/delete/",
        DeleteMessageAPIView.as_view(),
        name="message-delete",
    ),

    path(
        "messages/delete-for-me/",
        DeleteForMeAPIView.as_view(),
        name="message-delete-for-me",
    ),


    path(
        "rooms/<int:room_id>/messages/search/",
        SearchMessagesAPIView.as_view(),
        name="message-search",
    ),

    path(
        "messages/<int:pk>/",
        UpdateMessageAPIView.as_view(),
        name="message-update",
    ),

    # ==========================
    # Participants
    # ==========================

    
    path(
        "rooms/<int:room_id>/participants/",
        AddParticipantAPIView.as_view(),
        name="participant-add",
    ),
    path(
        "rooms/<int:room_id>/participants/<int:user_id>/",
        RemoveParticipantAPIView.as_view(),
        name="participant-remove",
    ),
    path(
        "rooms/<int:room_id>/leave/",
        LeaveGroupAPIView.as_view(),
        name="leave-group",
    ),
]