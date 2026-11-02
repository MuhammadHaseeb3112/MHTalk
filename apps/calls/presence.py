"""
Which WebSocket (channel name) each user's call screen is connected on.

Kept in the shared cache (Redis in production), not in process memory, so
call signalling (offer / answer / ICE) reaches the other person even when
their socket is held by a different server worker. Channel names are global
in the Redis channel layer, so any worker can send to any of them.
"""

from django.core.cache import cache

# Long enough for any call; refreshed on every connect.
_TTL_SECONDS = 6 * 60 * 60


def _key(user_id):
    return f"call_channel:{int(user_id)}"


async def set_call_channel(user_id, channel_name):
    await cache.aset(_key(user_id), channel_name, _TTL_SECONDS)


async def get_call_channel(user_id):
    return await cache.aget(_key(user_id))


async def clear_call_channel(user_id, channel_name):
    """Forget the mapping only if it still points at this socket (newer tabs win)."""
    if await cache.aget(_key(user_id)) == channel_name:
        await cache.adelete(_key(user_id))
