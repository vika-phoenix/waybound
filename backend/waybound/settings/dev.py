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

# ── Admin redirect ────────────────────────────────────────────────
LOGIN_REDIRECT_URL = '/admin/'

# ── Cookies: local dev is HTTP — override any Railway .env values ─
# Secure=True → browser only sends cookie over HTTPS → admin loops back to login
# SameSite=None requires Secure=True → Chrome drops the cookie entirely → 403 CSRF
SESSION_COOKIE_SECURE   = False
CSRF_COOKIE_SECURE      = False
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE    = 'Lax'

# ── Debug toolbar (optional — uncomment if installed) ─────────
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE  += ['debug_toolbar.middleware.DebugToolbarMiddleware']
# INTERNAL_IPS = ['127.0.0.1']
