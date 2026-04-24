from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = SECRET_KEY or "dev-only-change-me"  # noqa: F405

ALLOWED_HOSTS = ALLOWED_HOSTS or [  # noqa: F405
    "localhost",
    "127.0.0.1",
    "backend",
]

CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS or [  # noqa: F405
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

CSRF_TRUSTED_ORIGINS = CSRF_TRUSTED_ORIGINS or [  # noqa: F405
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

AUTH_COOKIE_SECURE = False
AUTH_COOKIE_SAMESITE = "Lax"
FRONTEND_BASE_URL = FRONTEND_BASE_URL or "http://localhost:3000"  # noqa: F405
