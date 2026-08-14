"""
waybound/settings/base.py
Settings shared across ALL environments (dev, prod).
Never import this directly — import dev.py or prod.py.
"""
from pathlib import Path
from decouple import config, Csv

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ── Security ──────────────────────────────────────────────────
SECRET_KEY = config('DJANGO_SECRET_KEY')
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')
ALLOWED_HOSTS = config('DJANGO_ALLOWED_HOSTS', cast=Csv(), default='localhost,127.0.0.1')

# ── Applications ──────────────────────────────────────────────
DJANGO_APPS = [
    'jazzmin',                 # must come before django.contrib.admin
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',          # required by allauth
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # needed for logout token invalidation
    'corsheaders',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    # 'allauth.socialaccount.providers.apple',  # removed — requires paid Apple Developer account
    'allauth.socialaccount.providers.yandex',
    'allauth.socialaccount.providers.vk',
    'django_filters',
    'django_extensions',
    'django_apscheduler',
]

LOCAL_APPS = [
    'apps.users',
    'apps.tours',
    'apps.bookings',
    'apps.reviews',
    'apps.payments',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware ────────────────────────────────────────────────
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',          # must be first
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',   # required by allauth 0.56+
]

ROOT_URLCONF = 'waybound.urls'

# ── Templates ─────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',  # required by allauth
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'waybound.wsgi.application'

# ── Password validation ───────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internationalisation ──────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ── Static & media ────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Custom user model ────────────────────────────────────────
AUTH_USER_MODEL = 'users.User'

# ── REST Framework ────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# ── JWT ───────────────────────────────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ── Session cookies — must be SameSite=None so the allauth session cookie
# is sent on the cross-origin /api/v1/auth/social/token/ fetch from the
# frontend (different origin than Django during local dev).
# On production (same ngrok/Railway domain not needed) these are set via env.
SESSION_COOKIE_SAMESITE = config('SESSION_COOKIE_SAMESITE', default='Lax')
SESSION_COOKIE_SECURE   = config('SESSION_COOKIE_SECURE',   default=False, cast=bool)
CSRF_COOKIE_SAMESITE    = config('CSRF_COOKIE_SAMESITE',    default='Lax')
CSRF_COOKIE_SECURE      = config('CSRF_COOKIE_SECURE',      default=False, cast=bool)

# ── CORS ──────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    cast=Csv(),
    default='http://localhost:8080,http://127.0.0.1:8080',
)
# Allow all Cloudflare Pages preview deployments (*.waybound.pages.dev)
CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^https://[a-z0-9]+\.waybound\.pages\.dev$',
]
CORS_ALLOW_CREDENTIALS = True

# ── django-allauth ────────────────────────────────────────────
SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
ACCOUNT_EMAIL_REQUIRED        = True
ACCOUNT_USERNAME_REQUIRED     = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_VERIFICATION    = config('ACCOUNT_EMAIL_VERIFICATION', default='optional')
ACCOUNT_USER_MODEL_USERNAME_FIELD = None

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        # Credentials live in the DB SocialApp record (populated by migration).
        # Do NOT add 'APP' here — allauth 0.62 would create a second in-memory
        # app and get_app() would raise MultipleObjectsReturned.
    },
    'yandex': {},
    'vk': {
        'SCOPE': ['email'],
    },
}
# If same email already exists from email/pw login, link the social account to it
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
# Skip the allauth "Sign in via X" confirmation page — go straight through
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True

# ── Custom allauth adapters (Tasks 10-11) ─────────────────────
ACCOUNT_ADAPTER        = 'apps.users.social_adapter.AccountAdapter'
SOCIALACCOUNT_ADAPTER  = 'apps.users.social_adapter.SocialAccountAdapter'

# Frontend URL — where to redirect after OAuth callback
# Change to your real domain in prod .env
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:8080')

# Cloudflare Pages preview deployments need to be trusted for CSRF
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    cast=Csv(),
    default='http://localhost:8080,http://127.0.0.1:8080',
)

# ── Email ─────────────────────────────────────────────────────
# For local dev: set EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend in .env
# Emails will print to the runserver terminal — no real sending needed.
EMAIL_BACKEND      = config('EMAIL_BACKEND',      default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST         = config('EMAIL_HOST',          default='smtp.gmail.com')
EMAIL_PORT         = config('EMAIL_PORT',          default=587, cast=int)
EMAIL_USE_TLS      = config('EMAIL_USE_TLS',       default=True, cast=bool)
EMAIL_HOST_USER    = config('EMAIL_HOST_USER',     default='')
EMAIL_HOST_PASSWORD= config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL        = config('DEFAULT_FROM_EMAIL',        default='noreply@kavkazland.com')
# Where verification uploads, tour submissions and tour-change alerts land.
# Deliberately empty rather than a real address: a working default is the worst
# kind, because forgetting to set it looks identical to having set it — the
# moderation queue just quietly goes to whoever is baked in here. Empty makes
# the helpers fall back to DEFAULT_FROM_EMAIL and log a warning, so the
# misconfiguration is visible. Set a role address (admin@kavkazland.com), not a
# personal inbox, so it survives one person being away or leaving.
ADMIN_NOTIFICATION_EMAIL  = config('ADMIN_NOTIFICATION_EMAIL',  default='')

# ── YooKassa ─────────────────────────────────────────────────
YOOKASSA_SHOP_ID    = config('YOOKASSA_SHOP_ID', default='')
YOOKASSA_SECRET_KEY = config('YOOKASSA_SECRET_KEY', default='')

# ── Payment rails ─────────────────────────────────────────────
# Two independent rails settling to two different bank accounts:
#   * Russian      — YooKassa / SBP, charges RUB, settles to the Russian account
#   * International— Stripe / PayPal, charges USD, settles to the other account
# Each provider carries its own credentials, so the money routes itself; the
# provider used is recorded on Booking.payment_method for reconciliation.
#
# PAYMENT_METHODS_ENABLED is what the checkout actually offers. The frontend
# renders whatever GET /api/v1/payments/methods/ returns, so turning the
# Russian rail back on is this one env var — no code change, no redeploy.
# A method is only offered if it is BOTH listed here and configured.
PAYMENT_METHODS_ENABLED = config(
    'PAYMENT_METHODS_ENABLED', cast=Csv(), default='stripe,paypal',
)

STRIPE_SECRET_KEY      = config('STRIPE_SECRET_KEY',      default='')
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY', default='')
STRIPE_WEBHOOK_SECRET  = config('STRIPE_WEBHOOK_SECRET',  default='')

PAYPAL_CLIENT_ID     = config('PAYPAL_CLIENT_ID',     default='')
PAYPAL_CLIENT_SECRET = config('PAYPAL_CLIENT_SECRET', default='')
PAYPAL_WEBHOOK_ID    = config('PAYPAL_WEBHOOK_ID',    default='')
# 'sandbox' until a live PayPal business account exists.
PAYPAL_ENV           = config('PAYPAL_ENV', default='sandbox')

# YooKassa does not sign webhooks — it authenticates by source IP. Empty means
# "don't check", which is the current (insecure) behaviour; set it in prod.
# Published list: https://yookassa.ru/developers/using-api/webhooks
YOOKASSA_WEBHOOK_IPS = config('YOOKASSA_WEBHOOK_IPS', cast=Csv(), default='')

# ── Telegram ──────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = config('TELEGRAM_BOT_TOKEN', default='')

# ── APScheduler ───────────────────────────────────────────────
APSCHEDULER_DATETIME_FORMAT = 'N j, Y, f:s a'
APSCHEDULER_RUN_NOW_TIMEOUT = 25  # seconds

# ── Jazzmin (admin UI) ────────────────────────────────────────
JAZZMIN_SETTINGS = {
    # ── Branding ──────────────────────────────────────────────
    'site_title':        'Kavkazland Admin',
    'site_header':       'Kavkazland',
    'site_brand':        'Kavkazland',
    'welcome_sign':      'Welcome to Kavkazland Admin',
    'copyright':         'Kavkazland',

    # ── Top menu ──────────────────────────────────────────────
    'topmenu_links': [
        {'name': 'Home', 'url': 'admin:index', 'permissions': ['auth.view_user']},
        {'app': 'bookings'},
        {'app': 'tours'},
        {'app': 'users'},
        {'app': 'reviews'},
        {'app': 'payments'},
    ],

    # ── Side menu ──────────────────────────────────────────────
    'show_sidebar':     True,
    'navigation_expanded': True,
    'hide_apps':        [],
    'hide_models':      [],

    # ── Order models in sidebar ───────────────────────────────
    'order_with_respect_to': [
        'bookings', 'bookings.Booking', 'bookings.EnquiryMessage',
        'tours', 'tours.Tour', 'tours.DepartureDate',
        'users', 'users.User', 'users.VerificationDocument',
        'reviews', 'reviews.TourReview',
        'payments',
        'auth', 'auth.Group',
    ],

    # ── Icons (Font Awesome 5 classes) ────────────────────────
    'icons': {
        'auth':                      'fas fa-users-cog',
        'auth.Group':                'fas fa-layer-group',
        'users.User':                'fas fa-user',
        'users.VerificationDocument':'fas fa-id-card',
        'bookings.Booking':          'fas fa-calendar-check',
        'bookings.EnquiryMessage':   'fas fa-envelope',
        'tours.Tour':                'fas fa-map-marked-alt',
        'tours.DepartureDate':       'fas fa-plane-departure',
        'reviews.TourReview':        'fas fa-star',
        'django_apscheduler.DjangoJob': 'fas fa-clock',
        'django_apscheduler.DjangoJobExecution': 'fas fa-history',
    },
    'default_icon_parents': 'fas fa-folder',
    'default_icon_children': 'fas fa-circle',

    # ── UI tweaks ─────────────────────────────────────────────
    'related_modal_active': True,    # open FK/M2M selects in a modal
    'show_ui_builder':      False,   # hide the UI customiser from non-developers
    'changeform_format':    'horizontal_tabs',
    'language_chooser':     False,
}

JAZZMIN_UI_TWEAKS = {
    'navbar_small_text':  False,
    'footer_small_text':  False,
    'body_small_text':    False,
    'brand_small_text':   False,
    'brand_colour':       'navbar-dark',
    'accent':             'accent-primary',
    'navbar':             'navbar-dark',
    'no_navbar_border':   True,
    'navbar_fixed':       True,
    'layout_boxed':       False,
    'footer_fixed':       False,
    'sidebar_fixed':      True,
    'sidebar':            'sidebar-dark-primary',
    'sidebar_nav_small_text': False,
    'sidebar_disable_expand': False,
    'sidebar_nav_child_indent': True,
    'sidebar_nav_compact_style': False,
    'sidebar_nav_legacy_style': False,
    'sidebar_nav_flat_style': False,
    'theme':              'default',
    'dark_mode_theme':    None,
    'button_classes': {
        'primary':   'btn-primary',
        'secondary': 'btn-secondary',
        'info':      'btn-info',
        'warning':   'btn-warning',
        'danger':    'btn-danger',
        'success':   'btn-success',
    },
}
