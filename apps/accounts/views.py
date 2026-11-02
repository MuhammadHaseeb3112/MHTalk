from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework import serializers

from rest_framework_simplejwt.tokens import RefreshToken

from .models import Profile, Contact, User
from .utils import broadcast_presence_refresh, normalize_phone_variants, notify_profile_changed
from .serializers import (
    DeleteAccountSerializer,
    PrivacySettingsSerializer,
    LoginSerializer,
    ProfileSerializer,
    UserRegistrationSerializer,
    UserSerializer,
    LogoutSerializer,
)


from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
)

class RegisterAPIView(APIView):
    """
    Register a new user.
    """

    permission_classes = [AllowAny]
    # Brute-force protection: THROTTLE_AUTH requests/minute per IP.
    throttle_scope = "auth"

    @extend_schema(
        summary="Register User",
        request=UserRegistrationSerializer,
        description="""
        Register a new user account.

        Creates a new account using the provided information.
        """,
        responses={
            201: OpenApiResponse(
                description="User registered successfully.",
            ),
            400: OpenApiResponse(
                description="Validation error.",
            ),
        },
        tags=["Accounts"],
    )

    

    def post( self, request,) -> Response:

        serializer = UserRegistrationSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()
            # Return tokens so the client can sign the new user in immediately.
            refresh = RefreshToken.for_user(user)

            return Response(
                {
                    "message": "User registered successfully.",
                    "user": UserSerializer(user, context={"viewer": user}).data,
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


class LoginAPIView(APIView):
    """
    Authenticate a user and return JWT tokens.
    """

    permission_classes = [AllowAny]
    # Brute-force protection: THROTTLE_AUTH requests/minute per IP.
    throttle_scope = "auth"

    @extend_schema(
        summary="Login",
        request=LoginSerializer,
        description="""
        Authenticate a user and return JWT access and refresh tokens.
        """,
        responses={
            200: OpenApiResponse(
                description="Login successful.",
            ),
            400: OpenApiResponse(
                description="Invalid credentials.",
            ),
        },
        tags=["Accounts"],
    )

    def post( self, request,) -> Response:

        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data["user"]

            refresh = RefreshToken.for_user(user)

            return Response(
                {
                    "message": "Login successful.",
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "user": UserSerializer(user, context={"viewer": user}).data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


class LogoutAPIView(APIView):
    """
    Logout a user by blacklisting the refresh token.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Logout",
        request=LogoutSerializer,
        description="""
        Logout the authenticated user.

        Invalidates the refresh token.
        """,
        responses={
            200: OpenApiResponse(
                description="Logout successful.",
            ),
            401: OpenApiResponse(
                description="Authentication required.",
            ),
        },
        tags=["Accounts"],
    )

    def post( self, request,) -> Response:
        try:
            refresh_token = request.data.get("refresh")

            token = RefreshToken(refresh_token)

            token.blacklist()

            return Response(
                {
                    "message": "Logout successful."
                },
                status=status.HTTP_200_OK,
            )

        except Exception:
            return Response(
                {
                    "error": "Invalid refresh token."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class MeAPIView(APIView):
    """
    Return the currently authenticated user.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Current User",
        description="""
        Retrieve the authenticated user's profile.
        """,
        responses={
            200: UserSerializer,
            401: OpenApiResponse(
                description="Authentication required.",
            ),
        },
        tags=["Accounts"],
    )

    def get(self, request):
        serializer = UserSerializer(request.user, context={"request": request})

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class UpdateProfileAPIView(APIView):
    """
    Update the authenticated user's profile.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Update Profile",
        request=ProfileSerializer,
        description="""
        Update the authenticated user's profile.
        """,
        responses={
            200: OpenApiResponse(
                description="Profile updated successfully.",
            ),
            400: OpenApiResponse(
                description="Validation error.",
            ),
        },
        tags=["Accounts"],
    )

    def patch(self, request):
        profile = request.user.profile
        remove_picture = str(request.data.get("remove_picture", "")).lower() in ("1", "true", "on", "yes")
        data = {
            key: request.data.get(key)
            for key in ("display_name", "about", "profile_picture")
            if key in request.data
        }

        serializer = ProfileSerializer(
            profile,
            data=data,
            partial=True,
        )

        if serializer.is_valid():
            if remove_picture and profile.profile_picture:
                profile.profile_picture.delete(save=False)
                profile.profile_picture = None
            serializer.save()
            notify_profile_changed(request.user)

            return Response(
                {
                    "message": "Profile updated successfully.",
                    "profile": serializer.data,
                    "user": UserSerializer(request.user, context={"request": request}).data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

class ContactSerializer(serializers.ModelSerializer):
    contact_user = UserSerializer(read_only=True)
    phone_number = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Contact
        fields = ("id", "name", "contact_user", "phone_number", "created_at")
        read_only_fields = ("id", "contact_user", "created_at")

    @staticmethod
    def _phone_variants(value):
        """Resolve common local/international formats to the account's stored phone."""
        return normalize_phone_variants(value)

    def validate(self, attrs):
        request = self.context["request"]
        if self.instance is None or "phone_number" in attrs:
            phone = str(attrs.get("phone_number", "")).strip()
            variants = self._phone_variants(phone)
            if not variants:
                raise serializers.ValidationError({"phone_number": "Phone number is required."})
            target = User.objects.filter(phone_number__in=variants, is_active=True).order_by("id").first()
            if target is None:
                raise serializers.ValidationError({"phone_number": "No active MHTalk account was found for this number. Try the number with country code, e.g. +923001234567."})
            if target.pk == request.user.pk:
                raise serializers.ValidationError({"phone_number": "You cannot add yourself as a contact."})
            duplicates = Contact.objects.filter(owner=request.user, contact_user=target)
            if self.instance is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError({"phone_number": "This contact is already saved."})
            attrs["contact_user_obj"] = target
        return attrs

    def create(self, validated_data):
        target = validated_data.pop("contact_user_obj")
        validated_data.pop("phone_number", None)
        return Contact.objects.create(owner=self.context["request"].user, contact_user=target, **validated_data)

    def update(self, instance, validated_data):
        target = validated_data.pop("contact_user_obj", None)
        validated_data.pop("phone_number", None)
        if target is not None:
            instance.contact_user = target
        if "name" in validated_data:
            instance.name = validated_data["name"]
        instance.save()
        return instance


def _notify_contacts_changed(user):
    """Keep every open tab of the owner in sync after a contact change."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"chat_inbox_{user.pk}",
        {"type": "inbox.contacts_changed"},
    )


class ContactListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ContactSerializer

    def perform_create(self, serializer):
        serializer.save()
        _notify_contacts_changed(self.request.user)

    def get_queryset(self):
        return Contact.objects.filter(owner=self.request.user).select_related("contact_user", "contact_user__profile").order_by("name", "contact_user__phone_number")


class ContactDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ContactSerializer

    def perform_update(self, serializer):
        serializer.save()
        _notify_contacts_changed(self.request.user)

    def perform_destroy(self, instance):
        instance.delete()
        _notify_contacts_changed(self.request.user)

    def get_queryset(self):
        return Contact.objects.filter(owner=self.request.user).select_related("contact_user", "contact_user__profile")



class UserLookupAPIView(APIView):
    """
    Find a registered MHTalk account by phone number.

    Used by "New contact" and "New chat" to validate a number before saving
    it. Only exact (normalised) phone matches are returned so the endpoint
    cannot be used to enumerate the user directory.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Look up an account by phone number", tags=["Accounts"])
    def get(self, request):
        phone = request.query_params.get("phone", "")
        variants = normalize_phone_variants(phone)
        if not variants:
            return Response({"detail": "Enter a phone number."}, status=status.HTTP_400_BAD_REQUEST)
        user = (
            User.objects.filter(phone_number__in=variants, is_active=True, is_deleted=False)
            .select_related("profile")
            .order_by("id")
            .first()
        )
        if user is None:
            return Response(
                {"detail": "This phone number isn't on MHTalk."},
                status=status.HTTP_404_NOT_FOUND,
            )
        saved = Contact.objects.filter(owner=request.user, contact_user=user).first()
        return Response({
            "user": UserSerializer(user, context={"request": request}).data,
            "is_self": user.pk == request.user.pk,
            "saved_contact": {"id": saved.id, "name": saved.name} if saved else None,
        })


class UserCommonGroupsAPIView(APIView):
    """Groups shared by the authenticated user and another user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Groups in common with a user", tags=["Accounts"])
    def get(self, request, pk):
        from apps.chat.choices import RoomType
        from apps.chat.models import ChatRoom, Participant

        rooms = list(
            ChatRoom.objects.filter(
                room_type=RoomType.GROUP,
                is_active=True,
                participants__user=request.user,
            )
            .filter(participants__user_id=pk)
            .distinct()
            .order_by("name")
        )
        saved_names = dict(
            Contact.objects.filter(owner=request.user).values_list("contact_user_id", "name")
        )
        members_by_room = {}
        for participant in (
            Participant.objects.filter(room__in=rooms)
            .select_related("user", "user__profile")
            .order_by("joined_at")
        ):
            members_by_room.setdefault(participant.room_id, []).append(participant.user)

        data = []
        for room in rooms:
            members = members_by_room.get(room.id, [])
            names = []
            for member in members:
                if member.pk == request.user.pk:
                    names.append("You")
                    continue
                profile = getattr(member, "profile", None)
                names.append(
                    (saved_names.get(member.pk) or "").strip()
                    or (getattr(profile, "display_name", "") or "").strip()
                    or member.phone_number
                )
            data.append({
                "id": room.id,
                "name": room.name,
                "photo": room.photo.url if room.photo else None,
                "participants_count": len(members),
                "member_names": names,
            })
        return Response(data)



class PrivacySettingsAPIView(APIView):
    """Settings > Privacy: last seen & online, profile photo, about, read receipts."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Privacy settings", responses={200: PrivacySettingsSerializer}, tags=["Accounts"])
    def get(self, request):
        return Response(PrivacySettingsSerializer(request.user.profile).data)

    @extend_schema(
        summary="Update privacy settings",
        request=PrivacySettingsSerializer,
        responses={200: PrivacySettingsSerializer},
        tags=["Accounts"],
    )
    def patch(self, request):
        profile = request.user.profile
        serializer = PrivacySettingsSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Everyone who can see this user refreshes names/photos/about, and
        # gets presence re-filtered for them.
        notify_profile_changed(request.user)
        broadcast_presence_refresh(request.user)
        return Response(PrivacySettingsSerializer(profile).data)


class DeleteAccountAPIView(APIView):
    """Settings > Account > Delete account (confirm with phone number + password)."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    @extend_schema(summary="Delete my account", request=DeleteAccountSerializer, tags=["Accounts"])
    def post(self, request):
        from .deletion import delete_account

        serializer = DeleteAccountSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        delete_account(request.user)
        return Response({"message": "Your account was deleted."}, status=status.HTTP_200_OK)
