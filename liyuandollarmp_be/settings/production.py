from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

required_settings = {
    "DJANGO_SECRET_KEY": SECRET_KEY,  # noqa: F405
    "DJANGO_ALLOWED_HOSTS": ALLOWED_HOSTS,  # noqa: F405
    "DATABASE_URL": DATABASE_URL,  # noqa: F405
    "FRONTEND_BASE_URL": FRONTEND_BASE_URL,  # noqa: F405
}

missing_settings = [name for name, value in required_settings.items() if not value]
if missing_settings:
    joined = ", ".join(missing_settings)
    raise ImproperlyConfigured(f"Missing required production settings: {joined}")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
AUTH_COOKIE_SECURE = True
AUTH_COOKIE_SAMESITE = "Lax"

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
