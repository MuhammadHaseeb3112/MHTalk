from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from .choices import CallType

from .models import (
    Call,
    CallParticipant,
)


# ==========================================================
# Call Participant
# ==========================================================

class CallParticipantSerializer(serializers.ModelSerializer):

    user = UserSerializer(
        read_only=True,
    )

    class Meta:

        model = CallParticipant

        fields = (
            "id",
            "user",
            "joined_at",
            "left_at",
            "is_muted",
            "is_on_hold",
            "state",
            "answered_at",
        )

        read_only_fields = fields


# ==========================================================
# Call
# ==========================================================

class CallSerializer(serializers.ModelSerializer):

    caller = UserSerializer(
        read_only=True,
    )

    is_missed = serializers.SerializerMethodField()
    is_missed_seen = serializers.SerializerMethodField()
    is_outgoing = serializers.SerializerMethodField()
    room_type = serializers.CharField(source="room.room_type", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)

    def _user_id(self):
        request = self.context.get("request")
        return request.user.id if request and request.user.is_authenticated else None

    def get_is_missed(self, obj):
        from .events import is_missed_for

        user_id = self._user_id()
        return bool(user_id and is_missed_for(obj, user_id))

    def get_is_missed_seen(self, obj):
        user_id = self._user_id()
        if not user_id:
            return True
        row = next((p for p in obj.participants.all() if p.user_id == user_id), None)
        return bool(row and row.missed_seen_at)

    def get_is_outgoing(self, obj):
        return obj.caller_id == self._user_id()

    participants = CallParticipantSerializer(
        many=True,
        read_only=True,
    )

    class Meta:

        model = Call

        fields = (
            "id",
            "room",
            "caller",
            "call_type",
            "status",
            "started_at",
            "answered_at",
            "ended_at",
            "duration",
            "participants",
            "is_missed",
            "is_missed_seen",
            "is_outgoing",
            "room_type",
            "room_name",
            "is_group",
        )

        read_only_fields = fields



class StartCallSerializer(serializers.Serializer):

    room = serializers.IntegerField()

    call_type = serializers.ChoiceField(
        choices=CallType.choices
    )