"""
apps/users/social_adapter.py

After OAuth completes, allauth calls AccountAdapter.get_login_redirect_url.
We mint JWT tokens there and embed them in the redirect URL so the frontend
never needs a cross-origin cookie exchange (which browsers increasingly block).
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
        """
        Called by allauth after ANY login (social or email-confirmed).
        Mint JWT immediately and embed in redirect URL — no cross-origin
        cookie needed, works in all browsers.
        """
        from rest_framework_simplejwt.tokens import RefreshToken
        from apps.users.serializers import UserMeSerializer

        frontend = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080').rstrip('/')

        if request.user.is_authenticated:
            user = request.user
            refresh = RefreshToken.for_user(user)
            user_data = UserMeSerializer(user, context={'request': request}).data
            params = urlencode({
                'social_access':  str(refresh.access_token),
                'social_refresh': str(refresh),
                'social_user':    json.dumps(user_data, separators=(',', ':')),
            })
            return f'{frontend}/signin.html?{params}'

        return f'{frontend}/signin.html?social_error=auth_failed'

    def get_signup_redirect_url(self, request):
        return self.get_login_redirect_url(request)


class SocialAccountAdapter(DefaultSocialAccountAdapter):

    def is_open_for_signup(self, request, sociallogin):
        return True

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        if not user.email:
            provider = sociallogin.account.provider
            uid      = sociallogin.account.uid
            user.email = f'{provider}_{uid}_{uuid.uuid4().hex[:8]}@placeholder.waybound.com'
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        provider = sociallogin.account.provider
        extra = sociallogin.account.extra_data or {}
        update_fields = []

        if provider in ('google', 'yandex', 'apple'):
            user.email_verified = True
            update_fields.append('email_verified')

        # Fill in missing profile fields from provider data
        if not user.first_name:
            first = extra.get('first_name') or extra.get('given_name') or ''
            if first:
                user.first_name = first
                update_fields.append('first_name')
        if not user.last_name:
            last = extra.get('last_name') or extra.get('family_name') or ''
            if last:
                user.last_name = last
                update_fields.append('last_name')
        # Yandex returns default_phone.number
        if not user.phone:
            phone = (extra.get('default_phone') or {}).get('number') or extra.get('phone') or ''
            if phone:
                user.phone = phone
                update_fields.append('phone')

        if update_fields:
            user.save(update_fields=update_fields)
        return user

    def get_connect_redirect_url(self, request, socialaccount):
        frontend = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080').rstrip('/')
        return f'{frontend}/settings.html?social=connected'
