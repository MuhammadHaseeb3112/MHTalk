import ipaddress
from urllib.parse import urlparse

from rest_framework import serializers


class PushKeysSerializer(serializers.Serializer):
    p256dh = serializers.CharField(max_length=255)
    auth = serializers.CharField(max_length=255)


class PushSubscribeSerializer(serializers.Serializer):
    """The browser's ``PushSubscription.toJSON()`` plus the device preview setting."""

    endpoint = serializers.URLField(max_length=1000)
    keys = PushKeysSerializer()
    show_previews = serializers.BooleanField(required=False, default=True)

    def validate_endpoint(self, value):
        # The server POSTs to this URL, so only accept public HTTPS push
        # services (never localhost / private addresses).
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or host == "localhost" or host.endswith(".localhost"):
            raise serializers.ValidationError("Invalid push endpoint.")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return value
        if not address.is_global:
            raise serializers.ValidationError("Invalid push endpoint.")
        return value


class PushUnsubscribeSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=1000)
