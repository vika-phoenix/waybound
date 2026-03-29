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
      payment_method: 'yookassa' (default) | 'sbp' | 'bank'
    """
    booking_id    = request.data.get('booking_id')
    payment_method = request.data.get('payment_method', 'yookassa')
    payment_type   = request.data.get('payment_type', 'deposit')

    if not booking_id:
        return Response({'detail': 'booking_id required.'}, status=status.HTTP_400_BAD_REQUEST)

    booking = get_object_or_404(Booking, pk=booking_id)

    if booking.tourist != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your booking.'}, status=status.HTTP_403_FORBIDDEN)

    currency = booking.currency or 'RUB'

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

        if payment_method == 'bank':
            booking.payment_method = 'bank'
            booking.save(update_fields=['payment_method'])
            return Response({
                'status':    'pending_transfer',
                'reference': booking.reference,
                'amount':    balance_amount,
                'currency':  currency,
            })

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

    if payment_method == 'bank':
        booking.payment_method   = 'bank'
        booking.balance_due_date = balance_due_date
        booking.save(update_fields=['payment_method', 'balance_due_date'])
        return Response({
            'status':      'pending_transfer',
            'reference':   booking.reference,
            'amount':      deposit_amount,
            'deposit_pct': deposit_pct,
            'currency':    currency,
        })

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


@api_view(['POST'])
@permission_classes([AllowAny])
def yookassa_webhook(request):
    """
    POST /api/v1/payments/webhook/
    YooKassa sends event notifications here.
    """
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
