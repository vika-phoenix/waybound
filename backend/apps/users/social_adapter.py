"""
apps/users/social_adapter.py
Custom allauth social adapter.

After OAuth completes, mint JWT tokens immediately and embed them in the
redirect URL so the frontend never needs a cross-origin cookie exchange.
This avoids SameSite/CORS cookie issues entirely.
"""
import json
import uuid
from urllib.parse import urlencode

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return True

    def get_login_redirect_url(self, request):
        # Fallback for non-social logins — shouldn't normally be called
        # for social flow since SocialAccountAdapter overrides it below.
        frontend = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080').rstrip('/')
        return frontend + '/signin.html?login=confirmed'


class SocialAccountAdapter(DefaultSocialAccountAdapter):

    def is_open_for_signup(self, request, sociallogin):
        return True

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        # VK sometimes returns no email — generate a placeholder
        if not user.email:
            provider = sociallogin.account.provider
            uid      = sociallogin.account.uid
            user.email = f'{provider}_{uid}_{uuid.uuid4().hex[:8]}@placeholder.waybound.com'
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        provider = sociallogin.account.provider
        if provider in ('google', 'yandex', 'apple'):
            user.email_verified = True
            user.save(update_fields=['email_verified'])
        return user

    def get_login_redirect_url(self, request):
        """
        Mint JWT tokens immediately after OAuth and embed them in the redirect
        URL. The frontend reads them from URL params and stores in localStorage.
        No cross-origin cookie needed — works in all browsers.
        """
        from rest_framework_simplejwt.tokens import RefreshToken
        from apps.users.serializers import UserMeSerializer

        frontend = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080').rstrip('/')

        if not request.user.is_authenticated:
            return frontend + '/signin.html?social_error=auth_failed'

        user = request.user
        refresh = RefreshToken.for_user(user)
        user_data = UserMeSerializer(user, context={'request': request}).data

        params = urlencode({
            'social_access':  str(refresh.access_token),
            'social_refresh': str(refresh),
            'social_user':    json.dumps(user_data, separators=(',', ':')),
        })
        return f'{frontend}/signin.html?{params}'

    def get_connect_redirect_url(self, request, socialaccount):
        """After connecting a social account from settings page."""
        from rest_framework_simplejwt.tokens import RefreshToken
        from apps.users.serializers import UserMeSerializer

        frontend = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080').rstrip('/')

        if not request.user.is_authenticated:
            return frontend + '/settings.html'

        user = request.user
        refresh = RefreshToken.for_user(user)
        user_data = UserMeSerializer(user, context={'request': request}).data

        params = urlencode({
            'social_access':  str(refresh.access_token),
            'social_refresh': str(refresh),
            'social_user':    json.dumps(user_data, separators=(',', ':')),
        })
        return f'{frontend}/settings.html?{params}'
