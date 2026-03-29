"""
apps/users/otp_service.py
OTP generation, storage, validation, and SMS dispatch.

SMS provider: SMSC.ru by default (popular in Russia, supports Mir/Russian numbers).
Swap send_sms() for Twilio or any other provider without changing anything else.

To use a different provider:
  1. Set SMS_PROVIDER=twilio in .env
  2. Add the provider's credentials to .env
  3. Update send_sms() below
"""
import random
import string
from datetime import timedelta

from django.utils import timezone
from django.conf import settings

from .models import OTPCode


# ── Config ────────────────────────────────────────────────────────────────
OTP_LENGTH        = 6
OTP_EXPIRY_MINUTES = 10   # code expires after 10 minutes
OTP_MAX_ATTEMPTS  = 5     # max failed verify attempts per phone per hour


def generate_code(length: int = OTP_LENGTH) -> str:
    """Return a random numeric string of given length."""
    return ''.join(random.choices(string.digits, k=length))


def create_otp(phone: str) -> OTPCode:
    """
    Invalidate any previous unused codes for this phone,
    create a fresh one, and return it.
    """
    # Expire old codes for this phone
    OTPCode.objects.filter(phone=phone, used=False).update(used=True)

    code = generate_code()
    otp = OTPCode.objects.create(phone=phone, code=code)
    return otp


def verify_otp(phone: str, code: str) -> tuple[bool, str]:
    """
    Check the code. Returns (True, '') on success,
    or (False, 'reason string') on failure.
    """
    expiry_cutoff = timezone.now() - timedelta(minutes=OTP_EXPIRY_MINUTES)

    otp = (
        OTPCode.objects
        .filter(phone=phone, used=False, created_at__gte=expiry_cutoff)
        .order_by('-created_at')
        .first()
    )

    if not otp:
        return False, 'Code expired or not found. Request a new one.'

    if otp.code != code:
        return False, 'Incorrect code.'

    otp.used = True
    otp.save(update_fields=['used'])
    return True, ''


# ── SMS dispatch ──────────────────────────────────────────────────────────

def send_sms(phone: str, code: str) -> bool:
    """
    Send the OTP via SMS. Returns True if dispatched, False on error.

    In development (DEBUG=True) the code is just printed to the console
    instead of actually sending an SMS — no SMS account needed locally.

    Production: uses SMSC.ru HTTP API.
    Register at smsc.ru, add SMSC_LOGIN and SMSC_PASSWORD to .env.

    Alternative providers you can swap in:
      - Twilio:        pip install twilio
      - MessageBird:   pip install messagebird
      - SMS.ru:        simple HTTP API, no package needed
    """
    message = f'Your Waybound code: {code}. Valid for {OTP_EXPIRY_MINUTES} minutes.'

    if getattr(settings, 'DEBUG', False):
        # ── Dev: print to console ──────────────────────────
        print(f'\n[OTP SMS — DEV] To: {phone}  |  {message}\n')
        return True

    # ── Prod: SMSC.ru ─────────────────────────────────────
    try:
        import urllib.request
        import urllib.parse

        login    = getattr(settings, 'SMSC_LOGIN', '')
        password = getattr(settings, 'SMSC_PASSWORD', '')

        if not login or not password:
            print('[OTP] SMSC_LOGIN / SMSC_PASSWORD not set — SMS not sent.')
            return False

        params = urllib.parse.urlencode({
            'login':   login,
            'psw':     password,
            'phones':  phone,
            'mes':     message,
            'fmt':     1,   # JSON response
            'charset': 'utf-8',
        })
        url = f'https://smsc.ru/sys/send.php?{params}'
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read().decode()
            # SMSC returns {"id":N,"cnt":N} on success, {"error":...} on fail
            if '"error"' in body:
                print(f'[OTP] SMSC error: {body}')
                return False
        return True

    except Exception as exc:
        print(f'[OTP] SMS send failed: {exc}')
        return False
