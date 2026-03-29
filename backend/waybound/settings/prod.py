"""
waybound/settings/prod.py
Production settings (Railway + PostgreSQL).
Deploy with:
  DJANGO_SETTINGS_MODULE=waybound.settings.prod gunicorn waybound.wsgi
"""
from .base import *  # noqa
import dj_database_url
from decouple import config

DEBUG = False

# ── Database: PostgreSQL ──────────────────────────────────────
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL'),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ── Security headers ──────────────────────────────────────────
SECURE_SSL_REDIRECT          = False   # Railway handles SSL at the proxy — no redirect needed
SESSION_COOKIE_SECURE        = True
CSRF_COOKIE_SECURE           = True
SECURE_HSTS_SECONDS          = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD          = True
SECURE_BROWSER_XSS_FILTER   = True
SECURE_CONTENT_TYPE_NOSNIFF  = True
X_FRAME_OPTIONS              = 'DENY'
CSRF_TRUSTED_ORIGINS         = config('CSRF_TRUSTED_ORIGINS', cast=Csv(), default='https://waybound-production.up.railway.app')
SECURE_PROXY_SSL_HEADER      = ('HTTP_X_FORWARDED_PROTO', 'https')

# ── Email: Brevo (Sendinblue) via django-anymail ──────────────
EMAIL_BACKEND = 'anymail.backends.brevo.EmailBackend'
ANYMAIL = {
    'BREVO_API_KEY': config('BREVO_API_KEY', default=''),
}
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='Waybound <noreply@waybound.com>')

# ── Static files: WhiteNoise (serves CSS/JS directly from Railway) ─
MIDDLEWARE = ['whitenoise.middleware.WhiteNoiseMiddleware'] + MIDDLEWARE  # noqa
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ── Media files: Cloudflare R2 (S3-compatible, free tier) ─────
DEFAULT_FILE_STORAGE     = 'storages.backends.s3boto3.S3Boto3Storage'
AWS_ACCESS_KEY_ID        = config('R2_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY    = config('R2_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME  = config('R2_BUCKET_NAME', default='waybound-media')
AWS_S3_ENDPOINT_URL      = config('R2_ENDPOINT_URL', default='')   # https://<accountid>.r2.cloudflarestorage.com
AWS_S3_REGION_NAME       = 'auto'
AWS_S3_FILE_OVERWRITE    = False
AWS_DEFAULT_ACL          = None   # R2 doesn't support ACLs — public access via bucket policy
AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
_media_url               = config('R2_PUBLIC_URL', default='/media/')
MEDIA_URL                = _media_url if _media_url.endswith('/') else _media_url + '/'

# ── Logging ───────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
