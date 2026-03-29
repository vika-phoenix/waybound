"""
apps/users/tokens.py
Central place to mint JWT tokens for a user.
Every auth method (email, Google, Yandex, VK, Apple, OTP) calls
get_tokens_for_user() and returns the same shaped response.
"""
from rest_framework_simplejwt.tokens import RefreshToken


def get_tokens_for_user(user):
    """
    Returns a dict with access + refresh JWT strings.
    Usage:
        tokens = get_tokens_for_user(user)
        return Response({'user': ..., **tokens})
    """
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }
