"""
waybound/settings/dev.py
Development-only settings.
Run with:  python manage.py runserver
(manage.py defaults to this file)
"""
from .base import *  # noqa

DEBUG = True

# ── Database: SQLite for local dev, no setup required ─────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ── Email: print to console instead of sending ────────────────
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ── Allauth: skip email verification in dev ───────────────────
ACCOUNT_EMAIL_VERIFICATION = 'none'

# ── CORS: allow all origins locally ──────────────────────────
CORS_ALLOW_ALL_ORIGINS = True

# ── Debug toolbar (optional — uncomment if installed) ─────────
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE  += ['debug_toolbar.middleware.DebugToolbarMiddleware']
# INTERNAL_IPS = ['127.0.0.1']
