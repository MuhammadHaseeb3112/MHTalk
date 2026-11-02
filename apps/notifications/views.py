from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import push
from .models import PushSubscription
from .serializers import PushSubscribeSerializer, PushUnsubscribeSerializer


class PushPublicKeyAPIView(APIView):
    """VAPID application server key the browser needs to subscribe."""

    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(summary="Web Push public key", tags=["Notifications"], responses={200: dict})
    def get(self, request):
        return Response({"enabled": push.push_enabled(), "public_key": push.public_key()})


class PushSubscribeAPIView(APIView):
    """Register (or refresh) this browser's push subscription for the current user."""

    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(summary="Subscribe to Web Push", tags=["Notifications"], request=PushSubscribeSerializer, responses={201: dict})
    def post(self, request):
        if not push.push_enabled():
            return Response({"detail": "Background notifications are not configured on this server."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        serializer = PushSubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        _, created = PushSubscription.objects.update_or_create(
            endpoint=data["endpoint"],
            defaults={
                # A shared browser that logs in as someone else moves the
                # subscription to the new account.
                "user": request.user,
                "p256dh": data["keys"]["p256dh"],
                "auth": data["keys"]["auth"],
                "show_previews": data.get("show_previews", True),
                "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:255],
            },
        )
        return Response({"subscribed": True}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PushUnsubscribeAPIView(APIView):
    """Forget this browser's push subscription (only the caller's own)."""

    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(summary="Unsubscribe from Web Push", tags=["Notifications"], request=PushUnsubscribeSerializer, responses={200: dict})
    def post(self, request):
        serializer = PushUnsubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        deleted, _ = PushSubscription.objects.filter(
            user=request.user, endpoint=serializer.validated_data["endpoint"]
        ).delete()
        return Response({"subscribed": False, "deleted": bool(deleted)})
