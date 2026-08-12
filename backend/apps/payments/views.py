"""
apps/payments/views.py

Endpoints:
  POST /api/v1/payments/initiate/  — create YooKassa payment, return confirmation_url
  POST /api/v1/payments/webhook/   — receive YooKassa event notifications
"""
import uuid
import logging
import requests as http_requests
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from apps.bookings.models import Booking
from apps.bookings.views import send_booking_notification

logger = logging.getLogger(__name__)

CBR_URL = 'https://www.cbr.ru/scripts/XML_daily.asp'
CBR_CACHE_KEY = 'cbr_rates'
CBR_CACHE_TTL = 86400  # 24 hours


def get_cbr_rate(currency: str) -> float:
    """
    Return how many RUB equal 1 unit of `currency` using CBR daily rates.
    Result is cached for 24 h. Returns 1.0 if currency is already RUB.
    Raises ValueError if currency is not found or CBR is unreachable.
    """
    currency = currency.upper()
    if currency == 'RUB':
        return 1.0

    rates = cache.get(CBR_CACHE_KEY)
    if rates is None:
        try:
            resp = http_requests.get(CBR_URL, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            rates = {}
            for valute in root.findall('Valute'):
                code    = valute.findtext('CharCode', '').upper()
                nominal = int(valute.findtext('Nominal', '1'))
                value   = float(valute.findtext('Value', '0').replace(',', '.'))
                rates[code] = value / nominal  # rate per 1 unit
            cache.set(CBR_CACHE_KEY, rates, CBR_CACHE_TTL)
            logger.info('CBR rates refreshed: %d currencies cached', len(rates))
        except Exception as exc:
            logger.error('Failed to fetch CBR rates: %s', exc)
            raise ValueError(f'Cannot fetch exchange rate for {currency}. Please try again later.')

    if currency not in rates:
        raise ValueError(f'Currency {currency} not found in CBR rates.')

    return rates[currency]


def convert_to_rub(amount: float, currency: str) -> tuple[float, float]:
    """
    Convert `amount` in `currency` to RUB.
    Returns (rub_amount, rate_used).
    """
    rate = get_cbr_rate(currency)
    rub = float(Decimal(str(amount * rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    return rub, rate


def _yoo_configure():
    import yookassa
    yookassa.Configuration.account_id = settings.YOOKASSA_SHOP_ID
    yookassa.Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
    return yookassa


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    """
    POST /api/v1/payments/initiate/
    Body: { booking_id, payment_method, payment_type }
      payment_type: 'deposit' (default) | 'balance'
      payment_method: 'yookassa' (default) | 'sbp'
    """
    booking_id    = request.data.get('booking_id')
    payment_method = request.data.get('payment_method', 'yookassa')
    payment_type   = request.data.get('payment_type', 'deposit')

    # Validate against what is actually switched on and configured, so a method
    # can never be charged through a rail the operator has turned off.
    from . import providers
    allowed = providers.enabled_codes()
    if payment_method not in allowed:
        return Response(
            {'detail': f'Payment method unavailable. Enabled: {", ".join(allowed) or "none"}.'},
            status=status.HTTP_400_BAD_REQUEST)

    if not booking_id:
        return Response({'detail': 'booking_id required.'}, status=status.HTTP_400_BAD_REQUEST)

    booking = get_object_or_404(Booking, pk=booking_id)

    if booking.tourist != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your booking.'}, status=status.HTTP_403_FORBIDDEN)

    currency = booking.currency or 'RUB'

    # ── International rail (USD, separate bank account) ────────
    if providers.rail_for(payment_method) == providers.RAIL_INTL:
        return _initiate_international(booking, payment_method, payment_type, currency)

    # ── Balance payment ────────────────────────────────────────
    if payment_type == 'balance':
        if booking.status != Booking.Status.CONFIRMED:
            return Response({'detail': 'Only confirmed bookings can pay the balance.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if booking.balance_status == 'paid':
            return Response({'detail': 'Balance already paid.'}, status=status.HTTP_400_BAD_REQUEST)

        balance_amount = round(float(booking.total_price) - float(booking.deposit_paid), 2)
        if balance_amount <= 0:
            return Response({'detail': 'No balance due.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rub_balance, balance_rate = convert_to_rub(balance_amount, currency)
            yookassa = _yoo_configure()
            return_url = (
                getattr(settings, 'FRONTEND_URL', 'http://localhost:5500')
                + f'/my-bookings.html?paid=balance&ref={booking.reference}'
            )
            payment_data = {
                'amount': {'value': f'{rub_balance:.2f}', 'currency': 'RUB'},
                'confirmation': {'type': 'redirect', 'return_url': return_url},
                'description': f'Balance — {booking.tour.title} ({booking.reference})',
                'metadata': {
                    'booking_id':   str(booking.id),
                    'booking_ref':  booking.reference,
                    'payment_type': 'balance',
                },
                'capture': True,
            }
            if payment_method == 'sbp':
                payment_data['payment_method_data'] = {'type': 'sbp'}

            payment = yookassa.Payment.create(payment_data, str(uuid.uuid4()))
            booking.balance_payment_id = payment.id
            booking.payment_method     = payment_method
            booking.save(update_fields=['balance_payment_id', 'payment_method'])
            resp = {'confirmation_url': payment.confirmation.confirmation_url}
            if currency != 'RUB':
                resp['rub_amount'] = rub_balance
                resp['exchange_rate'] = balance_rate
                resp['original_currency'] = currency
            return Response(resp)

        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error('YooKassa balance payment error: %s', exc, exc_info=True)
            return Response({'detail': 'Payment gateway error. Please try again.'},
                            status=status.HTTP_502_BAD_GATEWAY)

    # ── Deposit payment (default) ──────────────────────────────
    if booking.status != Booking.Status.PENDING:
        return Response({'detail': f'Booking is {booking.status}, not pending.'}, status=status.HTTP_400_BAD_REQUEST)
    if booking.deposit_status == 'paid':
        return Response({'detail': 'Deposit already paid.'}, status=status.HTTP_400_BAD_REQUEST)

    from apps.bookings.views import compute_dynamic_deposit_pct
    deposit_pct    = compute_dynamic_deposit_pct(booking)
    deposit_amount = round(float(booking.total_price) * deposit_pct / 100, 2)

    balance_due_days = getattr(booking.tour, 'balance_due_days', 30)
    if booking.departure_date:
        from datetime import timedelta, date as _date
        calculated = booking.departure_date - timedelta(days=balance_due_days)
        # If the departure is within balance_due_days, the balance is due today
        # (tourist booked late — don't show a past date as the due date)
        balance_due_date = max(calculated, _date.today())
    else:
        balance_due_date = None

    try:
        rub_deposit, deposit_rate = convert_to_rub(deposit_amount, currency)
        yookassa = _yoo_configure()
        return_url = (
            getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')
            + f'/booking-confirmation.html?ref={booking.reference}'
        )
        payment_data = {
            'amount': {'value': f'{rub_deposit:.2f}', 'currency': 'RUB'},
            'confirmation': {'type': 'redirect', 'return_url': return_url},
            'description': f'Deposit {deposit_pct}% — {booking.tour.title} ({booking.reference})',
            'metadata': {
                'booking_id':   str(booking.id),
                'booking_ref':  booking.reference,
                'payment_type': 'deposit',
            },
            'capture': True,
        }
        if payment_method == 'sbp':
            payment_data['payment_method_data'] = {'type': 'sbp'}

        payment = yookassa.Payment.create(payment_data, str(uuid.uuid4()))
        booking.yookassa_payment_id = payment.id
        booking.payment_method      = payment_method
        booking.balance_due_date    = balance_due_date
        booking.save(update_fields=['yookassa_payment_id', 'payment_method', 'balance_due_date'])
        resp = {
            'confirmation_url': payment.confirmation.confirmation_url,
            'deposit_pct':      deposit_pct,
        }
        if currency != 'RUB':
            resp['rub_amount'] = rub_deposit
            resp['exchange_rate'] = deposit_rate
            resp['original_currency'] = currency
        return Response(resp)

    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        raw = getattr(getattr(exc, 'response', None), 'text', None)
        logger.error('YooKassa initiate_payment error: %s | payment_data=%s | raw_response=%s',
                     exc, payment_data, raw, exc_info=True)
        return Response({'detail': 'Payment gateway error. Please try again.'},
                        status=status.HTTP_502_BAD_GATEWAY)


def _client_ip(request):
    """Real client IP behind the Cloudflare -> Railway proxy chain."""
    cf = request.META.get('HTTP_CF_CONNECTING_IP')
    if cf:
        return cf.strip()
    fwd = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _yookassa_ip_allowed(request):
    """
    YooKassa does not sign its webhooks — it authenticates by source IP.

    Without this the endpoint accepts a `payment.succeeded` from anyone who
    knows a payment id, and the person most likely to know one is the customer
    who just started the payment and can read it from their own redirect. They
    could abandon the payment and confirm the booking themselves.

    An empty YOOKASSA_WEBHOOK_IPS keeps the old permissive behaviour so this
    can't break a live deploy the moment it ships; set it in production.
    Networks are listed at https://yookassa.ru/developers/using-api/webhooks
    """
    allowed = getattr(settings, 'YOOKASSA_WEBHOOK_IPS', [])
    if not allowed:
        logger.warning('YOOKASSA_WEBHOOK_IPS is unset — webhook is unauthenticated.')
        return True

    import ipaddress
    raw = _client_ip(request)
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        logger.warning('Webhook from unparseable IP %r — rejected.', raw)
        return False

    for net in allowed:
        try:
            if ip in ipaddress.ip_network(net.strip(), strict=False):
                return True
        except ValueError:
            logger.error('Bad network %r in YOOKASSA_WEBHOOK_IPS — skipped.', net)
    logger.warning('Webhook from disallowed IP %s — rejected.', raw)
    return False


@api_view(['POST'])
@permission_classes([AllowAny])
def yookassa_webhook(request):
    """
    POST /api/v1/payments/webhook/
    YooKassa sends event notifications here.
    """
    if not _yookassa_ip_allowed(request):
        return Response({'status': 'forbidden'}, status=status.HTTP_403_FORBIDDEN)
    try:
        event      = request.data
        event_type = event.get('event', '')
        obj        = event.get('object', {})
        payment_id = obj.get('id', '')

        if not payment_id:
            return Response({'status': 'ignored'})

        meta         = obj.get('metadata', {})
        payment_type = meta.get('payment_type', 'deposit')

        if event_type == 'payment.succeeded':
            amount = Decimal(obj.get('amount', {}).get('value', '0'))

            if payment_type == 'balance':
                # Balance payment succeeded
                try:
                    booking = Booking.objects.get(balance_payment_id=payment_id)
                    booking.balance_paid   = amount
                    booking.balance_status = 'paid'
                    booking.save(update_fields=['balance_paid', 'balance_status'])
                    logger.info('Balance paid for booking %s via YooKassa', booking.reference)
                    # Send confirmation email to tourist
                    from apps.bookings.views import send_booking_confirmed_emails
                    # Reuse confirmed email as "fully paid" notification (balance settled)
                except Booking.DoesNotExist:
                    logger.warning('Webhook: no booking for balance payment %s', payment_id)
            else:
                # Deposit payment succeeded
                try:
                    booking = Booking.objects.get(yookassa_payment_id=payment_id)
                    # Store deposit in tour's own currency so balance_due stays correct.
                    # Use dynamic deposit % (matches what was charged at initiation).
                    from apps.bookings.views import compute_dynamic_deposit_pct
                    deposit_pct = compute_dynamic_deposit_pct(booking)
                    deposit_in_tour_currency = round(float(booking.total_price) * deposit_pct / 100, 2)
                    booking.deposit_paid   = deposit_in_tour_currency
                    booking.deposit_status = 'paid'
                    # If deposit covers the full price (100% deposit policy), mark
                    # balance as paid too so balance-reminder jobs skip this booking.
                    update_fields = ['deposit_paid', 'deposit_status']
                    if deposit_in_tour_currency >= float(booking.total_price):
                        booking.balance_status = 'paid'
                        update_fields.append('balance_status')
                    booking.save(update_fields=update_fields)
                    logger.info('Deposit paid for booking %s, awaiting operator confirmation', booking.reference)
                except Booking.DoesNotExist:
                    logger.warning('Webhook: no booking for deposit payment %s', payment_id)

        elif event_type == 'payment.canceled':
            if payment_type == 'balance':
                try:
                    booking = Booking.objects.get(balance_payment_id=payment_id)
                    booking.balance_status = 'failed'
                    booking.save(update_fields=['balance_status'])
                except Booking.DoesNotExist:
                    pass
            else:
                try:
                    booking = Booking.objects.get(yookassa_payment_id=payment_id)
                    booking.deposit_status = 'failed'
                    booking.save(update_fields=['deposit_status'])
                    logger.info('Deposit payment cancelled for booking %s', booking.reference)
                except Booking.DoesNotExist:
                    pass

        return Response({'status': 'ok'})

    except Exception as exc:
        logger.error('YooKassa webhook error: %s', exc, exc_info=True)
        return Response({'status': 'error'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def payment_methods(request):
    """
    GET /api/v1/payments/methods/?lang=ru

    The checkout renders whatever this returns, so enabling or hiding a rail is
    a PAYMENT_METHODS_ENABLED env change rather than a frontend edit. A method
    only appears if it is both switched on and actually configured, so the UI
    can never show a button that 500s for want of credentials.
    """
    from . import providers
    lang = 'ru' if request.GET.get('lang') == 'ru' else 'en'
    return Response({'methods': providers.available_methods(lang)})


# ══════════════════════════════════════════════════════════════
#  International rail — Stripe / PayPal (USD)
# ══════════════════════════════════════════════════════════════

def _frontend(path):
    return getattr(settings, 'FRONTEND_URL', 'http://localhost:8080').rstrip('/') + path


def _initiate_international(booking, method, payment_type, currency):
    """
    Create a hosted checkout on Stripe or PayPal and hand back the redirect.

    Both charge USD. Tours still priced in RUB are converted here using the same
    cached CBR rates the Russian rail uses, so there is one FX source and
    nothing to re-price by hand. The converted amount comes back in the response
    so the UI can show what the customer will actually be charged.
    """
    from .international import (PaymentError, convert_to_usd,
                                create_paypal_order, create_stripe_checkout)
    from apps.bookings.views import compute_dynamic_deposit_pct

    balance_due_date = None
    if payment_type == 'balance':
        if booking.status != Booking.Status.CONFIRMED:
            return Response({'detail': 'Only confirmed bookings can pay the balance.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if booking.balance_status == 'paid':
            return Response({'detail': 'Balance already paid.'},
                            status=status.HTTP_400_BAD_REQUEST)
        amount = round(float(booking.total_price) - float(booking.deposit_paid), 2)
        if amount <= 0:
            return Response({'detail': 'No balance due.'}, status=status.HTTP_400_BAD_REQUEST)
        deposit_pct = None
        description = 'Balance - {} ({})'.format(booking.tour.title, booking.reference)
    else:
        deposit_pct = compute_dynamic_deposit_pct(booking)
        amount = round(float(booking.total_price) * deposit_pct / 100, 2)
        description = 'Deposit {}% - {} ({})'.format(
            deposit_pct, booking.tour.title, booking.reference)
        balance_due_days = getattr(booking.tour, 'balance_due_days', 30)
        if booking.departure_date:
            from datetime import timedelta, date as _date
            balance_due_date = max(
                booking.departure_date - timedelta(days=balance_due_days), _date.today())

    try:
        usd_amount, rate = convert_to_usd(amount, currency)
    except (PaymentError, ValueError) as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    success = _frontend('/booking-confirmation.html?ref={}&paid={}'.format(
        booking.reference, payment_type))
    cancel = _frontend('/booking.html?ref={}&cancelled=1'.format(booking.reference))

    try:
        if method == 'stripe':
            payment_id, redirect_url = create_stripe_checkout(
                booking, usd_amount, description, success, cancel, payment_type)
        else:
            payment_id, redirect_url = create_paypal_order(
                booking, usd_amount, description, success, cancel, payment_type)
    except PaymentError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    fields = ['payment_method']
    booking.payment_method = method
    if payment_type == 'balance':
        booking.balance_payment_id = payment_id
        fields.append('balance_payment_id')
    else:
        # Column is named for YooKassa but holds whichever provider charged it;
        # payment_method records which rail, and that is what reconciliation
        # against the two bank accounts keys off.
        booking.yookassa_payment_id = payment_id
        fields.append('yookassa_payment_id')
        if balance_due_date:
            booking.balance_due_date = balance_due_date
            fields.append('balance_due_date')
    booking.save(update_fields=fields)

    resp = {'confirmation_url': redirect_url, 'usd_amount': usd_amount, 'currency': 'USD'}
    if deposit_pct is not None:
        resp['deposit_pct'] = deposit_pct
    if currency != 'USD':
        resp['original_currency'] = currency
        resp['exchange_rate'] = round(rate, 6)
    return Response(resp)


def _find_booking(payment_id, payment_type):
    if not payment_id:
        return None
    field = 'balance_payment_id' if payment_type == 'balance' else 'yookassa_payment_id'
    return Booking.objects.filter(**{field: payment_id}).first()


def _settle(booking, payment_type, amount_usd):
    """
    Mark a booking paid. Idempotent on purpose — both providers retry webhooks,
    and a duplicate delivery must not double-count or re-send emails.
    """
    from apps.bookings.views import compute_dynamic_deposit_pct

    if payment_type == 'balance':
        if booking.balance_status == 'paid':
            return False
        if amount_usd:
            booking.balance_paid = amount_usd
        booking.balance_status = 'paid'
        booking.save(update_fields=['balance_paid', 'balance_status'])
        logger.info('Balance paid for %s via %s', booking.reference, booking.payment_method)
        return True

    if booking.deposit_status == 'paid':
        return False
    pct = compute_dynamic_deposit_pct(booking)
    # Store the deposit in the tour's own currency so balance_due stays correct
    # even though the customer was charged a converted USD amount.
    booking.deposit_paid = round(float(booking.total_price) * pct / 100, 2)
    booking.deposit_status = 'paid'
    if booking.status == Booking.Status.PENDING:
        booking.status = Booking.Status.CONFIRMED
    booking.save(update_fields=['deposit_paid', 'deposit_status', 'status'])
    logger.info('Deposit paid for %s via %s', booking.reference, booking.payment_method)

    try:
        from apps.bookings.views import send_booking_confirmed_emails
        send_booking_confirmed_emails(booking)
    except Exception as exc:
        logger.error('Confirmation email failed for %s: %s', booking.reference, exc)
    return True


@api_view(['POST'])
@permission_classes([AllowAny])
def stripe_webhook(request):
    """
    POST /api/v1/payments/stripe/webhook/

    Only a signature-verified checkout.session.completed settles a booking. The
    browser redirect proves nothing, because the customer controls it.
    """
    from .international import verify_stripe_event

    event = verify_stripe_event(request)
    if event is None:
        return Response({'status': 'invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

    if event.get('type') != 'checkout.session.completed':
        return Response({'status': 'ignored'})

    session = event['data']['object']
    if session.get('payment_status') != 'paid':
        return Response({'status': 'unpaid'})

    meta = session.get('metadata') or {}
    payment_type = meta.get('payment_type', 'deposit')
    booking = _find_booking(session.get('id', ''), payment_type)
    if not booking:
        logger.warning('Stripe webhook: no booking for session %s', session.get('id'))
        return Response({'status': 'unknown booking'})

    _settle(booking, payment_type, round((session.get('amount_total') or 0) / 100, 2))
    return Response({'status': 'ok'})


@api_view(['POST'])
@permission_classes([AllowAny])
def paypal_webhook(request):
    """
    POST /api/v1/payments/paypal/webhook/

    ORDER.APPROVED only means the customer clicked pay — the money does not move
    until capture, so we capture here and settle on the result.
    """
    import json as _json
    from .international import PaymentError, capture_paypal_order, verify_paypal_event

    event = verify_paypal_event(request)
    if event is None:
        return Response({'status': 'invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

    etype = event.get('event_type', '')
    resource = event.get('resource', {}) or {}

    if etype == 'CHECKOUT.ORDER.APPROVED':
        order_id = resource.get('id', '')
        units = resource.get('purchase_units') or [{}]
    elif etype == 'PAYMENT.CAPTURE.COMPLETED':
        order_id = ((resource.get('supplementary_data') or {})
                    .get('related_ids') or {}).get('order_id', '')
        units = [resource]
    else:
        return Response({'status': 'ignored'})

    payment_type = 'deposit'
    try:
        custom = units[0].get('custom_id') or ''
        if custom:
            payment_type = _json.loads(custom).get('payment_type', 'deposit')
    except (ValueError, AttributeError, IndexError):
        pass

    booking = _find_booking(order_id, payment_type)
    if not booking:
        logger.warning('PayPal webhook: no booking for order %s', order_id)
        return Response({'status': 'unknown booking'})

    amount = None
    if etype == 'CHECKOUT.ORDER.APPROVED':
        try:
            amount = capture_paypal_order(order_id)
        except PaymentError as exc:
            logger.error('PayPal capture failed for %s: %s', booking.reference, exc)
            return Response({'status': 'capture failed'},
                            status=status.HTTP_502_BAD_GATEWAY)
    else:
        try:
            amount = float((resource.get('amount') or {}).get('value', 0))
        except (TypeError, ValueError):
            amount = None

    _settle(booking, payment_type, amount)
    return Response({'status': 'ok'})
