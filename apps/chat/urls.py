from django.urls import path

from .assistant import AssistantAPIView
from .group_views import (
    GroupInviteLinkAPIView,
    GroupPermissionsAPIView,
    InviteJoinAPIView,
    InvitePreviewAPIView,
    ResetGroupInviteLinkAPIView,
)

from .views import (
    AddParticipantAPIView,
    ChatRoomDetailAPIView,
    ChatRoomListAPIView,
    CreateGroupChatAPIView,
    CreatePrivateChatAPIView,
    DeleteMessageAPIView,
    LeaveGroupAPIView,
    MessageListAPIView,
    MessageInfoAPIView,
    ChatRoomInfoAPIView,
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
    DeleteChatAPIView,
    ClearChatAPIView,
    DeleteMessagesForEveryoneAPIView,
    DeleteMessagesForMeAPIView,
    PinChatAPIView,
    FavoriteChatAPIView,
    MarkRoomReadAPIView,
    MarkAllReadAPIView,
    ParticipantAdminAPIView,
    RoomSharedMediaAPIView,
    AllSharedMediaAPIView,
    RoomPinnedMessagesAPIView,
    GlobalMessageSearchAPIView,
)

from .feature_views import (
    DisappearingMessagesAPIView,
    LinkPreviewAPIView,
    PollVoteAPIView,
    ViewOnceMediaAPIView,
)

app_name = "chat"

urlpatterns = [
    # ==========================
    # Polls, disappearing messages, view once, link previews
    # ==========================
    path("messages/<int:message_id>/poll/vote/", PollVoteAPIView.as_view(), name="poll-vote"),
    path("messages/<int:message_id>/view-once/", ViewOnceMediaAPIView.as_view(), name="view-once-media"),
    path("rooms/<int:pk>/disappearing/", DisappearingMessagesAPIView.as_view(), name="room-disappearing"),
    path("link-preview/", LinkPreviewAPIView.as_view(), name="link-preview"),
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
        "rooms/<int:pk>/delete/",
        DeleteChatAPIView.as_view(),
        name="room-delete-for-me",
    ),
    path(
        "rooms/<int:pk>/clear/",
        ClearChatAPIView.as_view(),
        name="room-clear-for-me",
    ),
    path(
        "rooms/<int:pk>/read/",
        MarkRoomReadAPIView.as_view(),
        name="room-mark-read",
    ),
    path(
        "rooms/read-all/",
        MarkAllReadAPIView.as_view(),
        name="rooms-mark-all-read",
    ),
    path(
        "rooms/pin/",
        PinChatAPIView.as_view(),
        name="room-pin",
    ),
    path(
        "rooms/favorite/",
        FavoriteChatAPIView.as_view(),
        name="room-favorite",
    ),
    path(
        "rooms/<int:pk>/media/",
        RoomSharedMediaAPIView.as_view(),
        name="room-media",
    ),
    path(
        "rooms/<int:pk>/pinned/",
        RoomPinnedMessagesAPIView.as_view(),
        name="room-pinned-messages",
    ),
    path(
        "media/",
        AllSharedMediaAPIView.as_view(),
        name="all-shared-media",
    ),
    path(
        "ai/",
        AssistantAPIView.as_view(),
        name="assistant",
    ),
    path(
        "rooms/<int:pk>/info/",
        ChatRoomInfoAPIView.as_view(),
        name="room-info",
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
        "messages/<int:message_id>/info/",
        MessageInfoAPIView.as_view(),
        name="message-info",
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
        "messages/delete-for-everyone/",
        DeleteMessagesForEveryoneAPIView.as_view(),
        name="messages-delete-for-everyone",
    ),
    path(
        "messages/delete-many-for-me/",
        DeleteMessagesForMeAPIView.as_view(),
        name="messages-delete-many-for-me",
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
        "rooms/<int:room_id>/participants/<int:user_id>/admin/",
        ParticipantAdminAPIView.as_view(),
        name="participant-admin",
    ),
    path(
        "messages/search/",
        GlobalMessageSearchAPIView.as_view(),
        name="message-search-global",
    ),
    path(
        "rooms/<int:room_id>/leave/",
        LeaveGroupAPIView.as_view(),
        name="leave-group",
    ),

    # ==========================
    # Group permissions & invite links
    # ==========================
    path("rooms/<int:pk>/permissions/", GroupPermissionsAPIView.as_view(), name="group-permissions"),
    path("rooms/<int:pk>/invite-link/", GroupInviteLinkAPIView.as_view(), name="group-invite-link"),
    path("rooms/<int:pk>/invite-link/reset/", ResetGroupInviteLinkAPIView.as_view(), name="group-invite-link-reset"),
    path("invite/<str:code>/", InvitePreviewAPIView.as_view(), name="group-invite-preview"),
    path("invite/<str:code>/join/", InviteJoinAPIView.as_view(), name="group-invite-join"),
]
