from django.urls import path

from .views import PushPublicKeyAPIView, PushSubscribeAPIView, PushUnsubscribeAPIView

app_name = "notifications"

urlpatterns = [
    path("push/public-key/", PushPublicKeyAPIView.as_view(), name="push-public-key"),
    path("push/subscribe/", PushSubscribeAPIView.as_view(), name="push-subscribe"),
    path("push/unsubscribe/", PushUnsubscribeAPIView.as_view(), name="push-unsubscribe"),
]
