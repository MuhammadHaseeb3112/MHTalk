from .base import *
from decouple import config


DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
]