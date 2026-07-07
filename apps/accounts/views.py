from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken

from .models import Profile
from .serializers import (
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

            return Response(
                {
                    "message": "User registered successfully.",
                    "user": UserSerializer(user).data,
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
                    "user": UserSerializer(user).data,
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
        serializer = UserSerializer(request.user)

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

        serializer = ProfileSerializer(
            profile,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()

            return Response(
                {
                    "message": "Profile updated successfully.",
                    "profile": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )