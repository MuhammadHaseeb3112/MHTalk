from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import User


class JWTAuthMiddleware(BaseMiddleware):
    """
    Authenticate WebSocket connections using
    a JWT access token.
    """

    async def __call__(
        self,
        scope,
        receive,
        send,
    ):
        """
        Resolve the authenticated user and attach
        it to the connection scope.
        """

        query_string = parse_qs(
            scope["query_string"].decode()
        )

        token = query_string.get(
            "token",
            [None],
        )[0]

        if token is None:
            scope["user"] = AnonymousUser()

        else:
            scope["user"] = await self.get_user(
                token,
            )

        return await super().__call__(
            scope,
            receive,
            send,
        )

    @database_sync_to_async
    def get_user(
        self,
        token: str,
    ):
        """
        Return the authenticated user for the
        supplied JWT token.
        """

        try:
            access_token = AccessToken(
                token,
            )

            user_id = access_token["user_id"]

            return User.objects.get(
                pk=user_id,
                is_active=True,
            )

        except Exception:
            return AnonymousUser()
        

def JWTAuthMiddlewareStack(inner):
    """
    Return the custom JWT middleware.
    """

    return JWTAuthMiddleware(inner)