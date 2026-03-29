"""
apps/users/views.py
All auth endpoints — Tasks 9, 10, 11, 12.

Task 9  — email + password:  register, login, logout, /me, change-password
Task 10 — social OAuth:      Google, Yandex, VK  (allauth handles the browser
                              redirect; these views handle the JWT exchange after)
Task 11 — Apple OAuth:       same pattern as Task 10, Apple-specific notes inline
Task 12 — Phone OTP:         otp/request, otp/verify
"""
from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from allauth.socialaccount.models import SocialAccount

from .models import User, OTPCode
from .serializers import (
    TouristRegisterSerializer,
    OperatorRegisterSerializer,
    LoginSerializer,
    UserMeSerializer,
    ChangePasswordSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
)
from .tokens import get_tokens_for_user
from .otp_service import create_otp, verify_otp, send_sms


# ════════════════════════════════════════════════════════════════
# TASK 9 — Email + password auth
# ════════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    """GET /api/v1/auth/health/  — quick server check."""
    return Response({'status': 'ok', 'app': 'users'})


@api_view(['POST'])
@permission_classes([AllowAny])
def register_tourist(request):
    """
    POST /api/v1/auth/register/tourist/
    Body: { email, password, password2, first_name, last_name }
    Returns: user profile + JWT tokens
    """
    serializer = TouristRegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()

    return Response(
        {
            'user':  UserMeSerializer(user, context={'request': request}).data,
            **get_tokens_for_user(user),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def register_operator(request):
    """
    POST /api/v1/auth/register/operator/
    Body: { email, password, password2, first_name, last_name,
            phone, company_name, country }
    Returns: user profile + JWT tokens
    """
    serializer = OperatorRegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()

    return Response(
        {
            'user':  UserMeSerializer(user, context={'request': request}).data,
            **get_tokens_for_user(user),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    POST /api/v1/auth/login/
    Body: { email, password }
    Returns: user profile + JWT tokens
    """
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data['user']

    # Update last_login
    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])

    return Response(
        {
            'user':  UserMeSerializer(user, context={'request': request}).data,
            **get_tokens_for_user(user),
        }
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    POST /api/v1/auth/logout/
    Body: { refresh }  — the refresh token to blacklist
    Blacklists the refresh token so it can't be used to get new access tokens.
    """
    refresh_token = request.data.get('refresh')
    if not refresh_token:
        return Response(
            {'error': 'refresh token is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
    except Exception:
        # Already blacklisted or invalid — still return 200 (idempotent)
        pass

    return Response({'detail': 'Logged out successfully.'})


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def me(request):
    """
    GET    /api/v1/auth/me/  — return logged-in user's full profile
    PATCH  /api/v1/auth/me/  — update first_name, last_name, bio, country, avatar, phone, marketing_emails
    DELETE /api/v1/auth/me/  — deactivate account (soft delete)
    """
    user = request.user

    if request.method == 'GET':
        return Response(UserMeSerializer(user, context={'request': request}).data)

    if request.method == 'DELETE':
        # Soft delete: deactivate and anonymize
        user.is_active = False
        user.first_name = ''
        user.last_name = ''
        user.bio = ''
        user.phone = ''
        if user.avatar:
            user.avatar.delete(save=False)
        user.save()
        # Blacklist all refresh tokens
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
            for token in OutstandingToken.objects.filter(user=user):
                try:
                    RefreshToken(token.token).blacklist()
                except Exception:
                    pass
        except Exception:
            pass
        return Response({'detail': 'Account deactivated.'}, status=status.HTTP_200_OK)

    # PATCH
    serializer = UserMeSerializer(user, data=request.data, partial=True, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    POST /api/v1/auth/change-password/
    Body: { current_password, new_password, new_password2 }
    """
    user = request.user
    serializer = ChangePasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    if not user.check_password(serializer.validated_data['current_password']):
        return Response(
            {'current_password': 'Current password is incorrect.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(serializer.validated_data['new_password'])
    user.save()

    # Keep the current session valid (Django util)
    update_session_auth_hash(request, user)

    return Response({'detail': 'Password changed successfully.'})


# ════════════════════════════════════════════════════════════════
# TASK 10 — Social OAuth: Google, Yandex, VK
# TASK 11 — Apple OAuth
#
# How the flow works:
#   1. Frontend links to:  GET /accounts/google/login/
#                           GET /accounts/yandex/login/
#                           GET /accounts/vk/login/
#                           GET /accounts/apple/login/
#      (These are allauth's built-in URLs, included via allauth.urls)
#
#   2. User authenticates with the provider in their browser.
#
#   3. Provider redirects back to:
#      /accounts/google/login/callback/  (etc.)
#      allauth handles it, creates/updates the User in the DB.
#
#   4. allauth calls our SocialAccountAdapter.save_user() (social_adapter.py),
#      then redirects the browser to FRONTEND_URL.
#
#   5. The frontend has a short-lived "social login done" page that calls:
#      POST /api/v1/auth/social/token/  (view below)
#      to exchange the Django session for a JWT pair.
#
# ── Why a separate /social/token/ endpoint? ──────────────────────────────
# allauth uses Django sessions (cookies). Our API uses JWT (Authorization header).
# This endpoint bridges the gap: if the user has an active Django session from
# allauth, we trust it and hand back JWT tokens.
# ─────────────────────────────────────────────────────────────────────────

@api_view(['POST'])
def social_token_exchange(request):
    """
    POST /api/v1/auth/social/token/
    Called by the frontend after allauth's OAuth callback redirects back.
    Requires the user to have an active Django session (set by allauth).
    Returns JWT tokens.

    No body required — we read the session user from request.user.
    """
    if not request.user.is_authenticated:
        return Response(
            {'error': 'No active session. Complete the OAuth flow first.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    user = request.user
    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])

    # Include which providers are connected — useful for the frontend
    connected = list(
        SocialAccount.objects.filter(user=user).values_list('provider', flat=True)
    )

    return Response(
        {
            'user':               UserMeSerializer(user, context={'request': request}).data,
            'connected_providers': connected,
            **get_tokens_for_user(user),
        }
    )


# ════════════════════════════════════════════════════════════════
# TASK 12 — Phone OTP auth
# ════════════════════════════════════════════════════════════════

@api_view(['POST'])
@permission_classes([AllowAny])
def otp_request(request):
    """
    POST /api/v1/auth/otp/request/
    Body: { phone }   e.g. "+79161234567"

    Generates a 6-digit code, stores it, sends it via SMS.
    In dev (DEBUG=True) the code is printed to the console instead.
    """
    serializer = OTPRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    phone = serializer.validated_data['phone']

    otp = create_otp(phone)
    sent = send_sms(phone, otp.code)

    if not sent and not settings.DEBUG:
        return Response(
            {'error': 'Failed to send SMS. Please try again.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({
        'detail': f'Code sent to {phone}.',
        # In dev only, echo the code back for easy testing
        **(({'dev_code': otp.code}) if settings.DEBUG else {}),
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def otp_verify(request):
    """
    POST /api/v1/auth/otp/verify/
    Body: { phone, code }

    Verifies the code. If correct:
      - Finds existing user with that phone, OR creates a new tourist account.
      - Returns user profile + JWT tokens (same shape as email login).
    """
    serializer = OTPVerifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    phone = serializer.validated_data['phone']
    code  = serializer.validated_data['code']

    ok, reason = verify_otp(phone, code)
    if not ok:
        return Response({'error': reason}, status=status.HTTP_400_BAD_REQUEST)

    # Get or create user by phone number
    user = User.objects.filter(phone=phone).first()
    if not user:
        # New user — create a minimal account
        # They can add email/name later in /me PATCH
        placeholder_email = f'phone_{phone.lstrip("+")}@placeholder.waybound.com'
        user = User.objects.create(
            email         = placeholder_email,
            phone         = phone,
            phone_verified = True,
            role          = User.Role.TOURIST,
        )
        user.set_unusable_password()
        user.save()
    else:
        if not user.phone_verified:
            user.phone_verified = True
            user.save(update_fields=['phone_verified'])

    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])

    return Response(
        {
            'user':  UserMeSerializer(user, context={'request': request}).data,
            **get_tokens_for_user(user),
        }
    )


# ════════════════════════════════════════════════════════════════
# PASSWORD RESET
#
# Flow:
#   1. User POSTs their email to /password-reset/
#   2. We generate a secure token and email a reset link
#      In dev: link prints to the Django console (no email account needed)
#      In prod: real email sent via Mailgun
#   3. Frontend reads uid + token from the link, shows "new password" form
#   4. User POSTs uid + token + new password to /password-reset/confirm/
#   5. Password changed, user can now log in normally
#
# Security: uses Django's built-in PasswordResetTokenGenerator.
# Tokens expire after PASSWORD_RESET_TIMEOUT seconds (default: 3 days).
# Each token is single-use — it invalidates once the password is changed.
# ════════════════════════════════════════════════════════════════

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import send_mail

from .serializers import PasswordResetRequestSerializer, PasswordResetConfirmSerializer

token_generator = PasswordResetTokenGenerator()


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_request(request):
    """
    POST /api/v1/auth/password-reset/
    Body: { "email": "user@example.com" }

    Always returns 200 even if email not found — prevents email enumeration
    (an attacker can't tell whether an account exists by watching the response).

    In dev: the reset link is printed to the Django console.
    In prod: sent to the user's inbox via Mailgun.
    """
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data['email']

    # Always return success — don't reveal whether email exists
    SUCCESS = Response({'detail': 'If that email is registered, a reset link has been sent.'})

    user = User.objects.filter(email=email, is_active=True).first()
    if not user:
        return SUCCESS

    # Build the reset link
    uid   = urlsafe_base64_encode(force_bytes(user.pk))
    token = token_generator.make_token(user)

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')
    reset_link   = f'{frontend_url}/reset-password.html?uid={uid}&token={token}'

    subject = 'Reset your Waybound password'
    message = (
        f'Hi {user.first_name or user.email},\n\n'
        f'You requested a password reset for your Waybound account.\n\n'
        f'Click the link below to set a new password:\n{reset_link}\n\n'
        f'This link expires in 24 hours and can only be used once.\n\n'
        f'If you did not request this, you can safely ignore this email.\n\n'
        f'The Waybound team'
    )

    if settings.DEBUG:
        # Dev: print to console so you can test without an email account
        print(f'\n{"="*60}')
        print(f'[PASSWORD RESET — DEV]')
        print(f'To:    {email}')
        print(f'Link:  {reset_link}')
        print(f'UID:   {uid}')
        print(f'Token: {token}')
        print(f'{"="*60}\n')
    else:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )

    return SUCCESS


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    """
    POST /api/v1/auth/password-reset/confirm/
    Body: { "uid": "...", "token": "...", "new_password": "...", "new_password2": "..." }

    Frontend gets uid and token from the URL query params of the reset link.
    Returns JWT tokens on success so the user is immediately logged in
    after resetting — no need to go to the login page again.
    """
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    # Decode uid back to user pk
    try:
        pk   = force_str(urlsafe_base64_decode(data['uid']))
        user = User.objects.get(pk=pk)
    except (User.DoesNotExist, ValueError, TypeError):
        return Response(
            {'error': 'Reset link is invalid or has expired.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate the token
    if not token_generator.check_token(user, data['token']):
        return Response(
            {'error': 'Reset link is invalid or has expired.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Set new password
    user.set_password(data['new_password'])
    user.save()

    # Return JWT tokens so user is logged in immediately
    return Response({
        'detail': 'Password reset successful. You are now logged in.',
        'user':   UserMeSerializer(user, context={'request': request}).data,
        **get_tokens_for_user(user),
    })


# ── Operator verification ───────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def verify_document(request):
    """POST /api/v1/auth/verify/ — operator uploads ID document."""
    from .models import VerificationDocument
    if request.user.role != 'operator':
        return Response({'detail': 'Only operators can submit verification documents.'},
                        status=status.HTTP_403_FORBIDDEN)
    doc_file = request.FILES.get('document')
    if not doc_file:
        return Response({'detail': 'No document file provided.'}, status=status.HTTP_400_BAD_REQUEST)

    vdoc, created = VerificationDocument.objects.get_or_create(operator=request.user)
    vdoc.document = doc_file
    vdoc.status   = VerificationDocument.Status.PENDING
    vdoc.reviewed_at = None
    vdoc.admin_notes = ''
    vdoc.save()
    return Response(
        {'status': 'pending', 'message': 'Document submitted. We will review within 48 hours.'},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# ── Social account connections ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def social_connections(request):
    """
    GET /api/v1/auth/social/connections/
    Returns list of connected social accounts for the current user.
    """
    accounts = SocialAccount.objects.filter(user=request.user)
    result = []
    for acc in accounts:
        result.append({
            'id': acc.id,
            'provider': acc.provider,
            'uid': acc.uid,
            'email': acc.extra_data.get('email', ''),
        })
    return Response(result)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def social_disconnect(request, provider):
    """
    DELETE /api/v1/auth/social/connections/<provider>/
    Disconnect a social account. User must have a password set or another
    social account linked (otherwise they'd be locked out).
    """
    accounts = SocialAccount.objects.filter(user=request.user, provider=provider)
    if not accounts.exists():
        return Response({'detail': 'This provider is not connected.'},
                        status=status.HTTP_404_NOT_FOUND)

    # Safety: ensure user won't be locked out
    user = request.user
    has_password = user.has_usable_password()
    other_socials = SocialAccount.objects.filter(user=user).exclude(provider=provider).count()
    if not has_password and other_socials == 0:
        return Response(
            {'detail': 'Cannot disconnect — you have no password set. '
                       'Set a password first or connect another provider.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    accounts.delete()
    return Response({'detail': f'{provider} disconnected.'})
