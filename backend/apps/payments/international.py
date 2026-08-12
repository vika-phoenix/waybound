"""
apps/payments/international.py

The international rail: Stripe Checkout and PayPal Orders v2, both charging USD
and settling to the international bank account. The Russian rail (YooKassa/SBP,
charging RUB) stays in views.py and settles elsewhere; the two never share
credentials, which is what keeps the money in the right account.

Both providers are hosted-checkout: we create a payment on their side, redirect
the customer to their page, and wait for a *webhook* to tell us it succeeded.
The browser redirect is never treated as proof of payment — the customer can
close the tab, or forge the return URL. Only a signature-verified webhook
marks a booking paid.
"""
import json
import logging

import requests
import stripe
from django.conf import settings

logger = logging.getLogger(__name__)

PAYPAL_HOSTS = {
    'sandbox': 'https://api-m.sandbox.paypal.com',
    'live':    'https://api-m.paypal.com',
}


class PaymentError(Exception):
    """Provider rejected the request, or is misconfigured."""


# ── Currency ──────────────────────────────────────────────────

def convert_to_usd(amount, currency):
    """
    Convert `amount` in `currency` to USD, returning (usd_amount, rate_used).

    Tours predating the USD default are priced in RUB, and both providers here
    charge USD, so the conversion happens at checkout rather than by re-pricing
    the tour. Reuses the same cached CBR daily rates as the Russian rail, so
    there is one source of truth for FX and nothing to maintain by hand.
    """
    from decimal import Decimal, ROUND_HALF_UP
    from .views import get_cbr_rate

    currency = (currency or 'USD').upper()
    if currency == 'USD':
        return round(float(amount), 2), 1.0

    # get_cbr_rate returns RUB per 1 unit of the currency.
    rub_per_unit = get_cbr_rate(currency) if currency != 'RUB' else 1.0
    rub_per_usd = get_cbr_rate('USD')
    if not rub_per_usd:
        raise PaymentError('Cannot determine the USD exchange rate right now.')

    rate = rub_per_unit / rub_per_usd          # target currency -> USD
    usd = Decimal(str(float(amount) * rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if usd <= 0:
        raise PaymentError('Converted amount must be greater than zero.')
    return float(usd), rate


# ── Stripe ────────────────────────────────────────────────────

def _stripe_ready():
    if not getattr(settings, 'STRIPE_SECRET_KEY', ''):
        raise PaymentError('Stripe is not configured.')
    stripe.api_key = settings.STRIPE_SECRET_KEY


def create_stripe_checkout(booking, amount_usd, description, success_url, cancel_url, payment_type):
    """Create a Stripe Checkout Session. Returns (session_id, redirect_url)."""
    _stripe_ready()
    try:
        session = stripe.checkout.Session.create(
            mode='payment',
            line_items=[{
                'quantity': 1,
                'price_data': {
                    'currency': 'usd',
                    # Stripe takes the smallest unit, so cents.
                    'unit_amount': int(round(float(amount_usd) * 100)),
                    'product_data': {'name': description},
                },
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=booking.reference,
            metadata={
                'booking_id':   str(booking.id),
                'booking_ref':  booking.reference,
                'payment_type': payment_type,
            },
        )
    except stripe.error.StripeError as exc:
        logger.error('Stripe checkout failed for %s: %s', booking.reference, exc)
        raise PaymentError('Card payment is unavailable right now. Please try again.')
    return session.id, session.url


def verify_stripe_event(request):
    """
    Return the Stripe event only if the signature checks out, else None.

    Without this the endpoint would accept any POST claiming a payment
    succeeded, which is how a booking gets confirmed without money moving.
    """
    secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
    if not secret:
        logger.error('STRIPE_WEBHOOK_SECRET unset — refusing to trust the webhook.')
        return None
    sig = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    try:
        return stripe.Webhook.construct_event(request.body, sig, secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        logger.warning('Rejected Stripe webhook: %s', exc)
        return None


# ── PayPal ────────────────────────────────────────────────────

def _paypal_base():
    env = getattr(settings, 'PAYPAL_ENV', 'sandbox').lower()
    return PAYPAL_HOSTS.get(env, PAYPAL_HOSTS['sandbox'])


def _paypal_token():
    cid = getattr(settings, 'PAYPAL_CLIENT_ID', '')
    sec = getattr(settings, 'PAYPAL_CLIENT_SECRET', '')
    if not (cid and sec):
        raise PaymentError('PayPal is not configured.')
    try:
        r = requests.post(
            f'{_paypal_base()}/v1/oauth2/token',
            auth=(cid, sec),
            data={'grant_type': 'client_credentials'},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()['access_token']
    except Exception as exc:
        logger.error('PayPal auth failed: %s', exc)
        raise PaymentError('PayPal is unavailable right now. Please try again.')


def create_paypal_order(booking, amount_usd, description, return_url, cancel_url, payment_type):
    """Create a PayPal order. Returns (order_id, approval_url)."""
    token = _paypal_token()
    payload = {
        'intent': 'CAPTURE',
        'purchase_units': [{
            'reference_id': booking.reference,
            # custom_id comes back on the webhook, so the booking is
            # identifiable even if the order id lookup ever misses.
            'custom_id': json.dumps({
                'booking_id': str(booking.id),
                'payment_type': payment_type,
            }),
            'description': description[:127],
            'amount': {'currency_code': 'USD', 'value': f'{float(amount_usd):.2f}'},
        }],
        'application_context': {
            'brand_name':  'Kavkazland',
            'user_action': 'PAY_NOW',
            'return_url':  return_url,
            'cancel_url':  cancel_url,
        },
    }
    try:
        r = requests.post(
            f'{_paypal_base()}/v2/checkout/orders',
            headers={'Authorization': f'Bearer {token}',
                     'Content-Type': 'application/json'},
            json=payload, timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.error('PayPal order failed for %s: %s', booking.reference, exc)
        raise PaymentError('PayPal is unavailable right now. Please try again.')

    approve = next((l['href'] for l in data.get('links', []) if l.get('rel') == 'approve'), None)
    if not approve:
        logger.error('PayPal order %s has no approve link: %s', data.get('id'), data)
        raise PaymentError('PayPal did not return a checkout link.')
    return data['id'], approve


def capture_paypal_order(order_id):
    """
    Capture an approved order — this is the step that actually takes the money.

    PayPal's CHECKOUT.ORDER.APPROVED only means the customer clicked pay; funds
    do not move until capture. Returns the captured USD amount, or None.
    """
    token = _paypal_token()
    try:
        r = requests.post(
            f'{_paypal_base()}/v2/checkout/orders/{order_id}/capture',
            headers={'Authorization': f'Bearer {token}',
                     'Content-Type': 'application/json'},
            timeout=20,
        )
        # 422 with ORDER_ALREADY_CAPTURED is fine — webhooks can arrive twice.
        if r.status_code == 422 and 'ORDER_ALREADY_CAPTURED' in r.text:
            logger.info('PayPal order %s already captured.', order_id)
            return None
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.error('PayPal capture failed for %s: %s', order_id, exc)
        raise PaymentError('Could not capture the PayPal payment.')

    try:
        cap = data['purchase_units'][0]['payments']['captures'][0]
        return float(cap['amount']['value'])
    except (KeyError, IndexError):
        logger.error('Unexpected PayPal capture shape for %s: %s', order_id, data)
        return None


def verify_paypal_event(request):
    """
    Return the PayPal event only if PayPal itself confirms the signature.

    PayPal has no local HMAC — you hand the headers back to their
    verify-webhook-signature endpoint and they answer SUCCESS or FAILURE.
    """
    webhook_id = getattr(settings, 'PAYPAL_WEBHOOK_ID', '')
    if not webhook_id:
        logger.error('PAYPAL_WEBHOOK_ID unset — refusing to trust the webhook.')
        return None
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        logger.warning('PayPal webhook body was not JSON.')
        return None

    headers = {k: request.META.get(f'HTTP_{k}', '') for k in (
        'PAYPAL_TRANSMISSION_ID', 'PAYPAL_TRANSMISSION_TIME',
        'PAYPAL_CERT_URL', 'PAYPAL_AUTH_ALGO', 'PAYPAL_TRANSMISSION_SIG',
    )}
    if not all(headers.values()):
        logger.warning('PayPal webhook missing signature headers.')
        return None

    try:
        token = _paypal_token()
        r = requests.post(
            f'{_paypal_base()}/v1/notifications/verify-webhook-signature',
            headers={'Authorization': f'Bearer {token}',
                     'Content-Type': 'application/json'},
            json={
                'transmission_id':   headers['PAYPAL_TRANSMISSION_ID'],
                'transmission_time': headers['PAYPAL_TRANSMISSION_TIME'],
                'cert_url':          headers['PAYPAL_CERT_URL'],
                'auth_algo':         headers['PAYPAL_AUTH_ALGO'],
                'transmission_sig':  headers['PAYPAL_TRANSMISSION_SIG'],
                'webhook_id':        webhook_id,
                'webhook_event':     body,
            },
            timeout=20,
        )
        r.raise_for_status()
        if r.json().get('verification_status') != 'SUCCESS':
            logger.warning('PayPal webhook signature not verified.')
            return None
    except Exception as exc:
        logger.error('PayPal signature verification errored: %s', exc)
        return None

    return body
