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
        )

        read_only_fields = fields


# ==========================================================
# Call
# ==========================================================

class CallSerializer(serializers.ModelSerializer):

    caller = UserSerializer(
        read_only=True,
    )

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
        )

        read_only_fields = fields



class StartCallSerializer(serializers.Serializer):

    room = serializers.IntegerField()

    call_type = serializers.ChoiceField(
        choices=CallType.choices
    )