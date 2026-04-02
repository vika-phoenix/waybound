"""
apps/users/social_adapter.py
Custom allauth social adapter.

Handles two problems that the default adapter doesn't solve for us:
  1. VK doesn't always return an email — we generate a placeholder so the
     User model (which requires a unique email) can still save.
  2. After any social login we mint a JWT and redirect the frontend to a
     URL it can read the token from, instead of doing a Django session login.

Register this in settings/base.py:
  SOCIALACCOUNT_ADAPTER = 'apps.users.social_adapter.SocialAccountAdapter'
"""
import uuid
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings


class AccountAdapter(DefaultAccountAdapter):
    """
    Overrides the default allauth account adapter.
    Prevents allauth from redirecting to its own signup/login pages
    (we handle all UI in our HTML pages).
    """
    def is_open_for_signup(self, request):
        return True

    def get_login_redirect_url(self, request):
        # Always redirect to the frontend signin page so the JS can exchange
        # the allauth session for a JWT. Never use the `next` param from the
        # OAuth URL — it contains the Railway domain, not the frontend domain.
        frontend = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080').rstrip('/')
        return frontend + '/signin.html?login=confirmed'


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter for social (OAuth) accounts.
    """

    def is_open_for_signup(self, request, sociallogin):
        return True

    def populate_user(self, request, sociallogin, data):
        """
        Called when a new social user is being created.
        Ensures we always have an email even when VK doesn't provide one.
        """
        user = super().populate_user(request, sociallogin, data)

        # VK sometimes returns no email — generate a unique placeholder
        if not user.email:
            provider = sociallogin.account.provider  # 'vk'
            uid      = sociallogin.account.uid
            user.email = f'{provider}_{uid}_{uuid.uuid4().hex[:8]}@placeholder.waybound.com'

        return user

    def save_user(self, request, sociallogin, form=None):
        """
        After saving, set email_verified=True for providers that
        guarantee a verified email (Google, Yandex, Apple).
        VK is not guaranteed so we leave it False.
        """
        user = super().save_user(request, sociallogin, form)
        provider = sociallogin.account.provider

        if provider in ('google', 'yandex', 'apple'):
            user.email_verified = True
            user.save(update_fields=['email_verified'])

        return user

    def get_connect_redirect_url(self, request, socialaccount):
        return getattr(settings, 'FRONTEND_URL', '/') + '?social=connected'
