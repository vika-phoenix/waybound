"""
apps/tours/telegram.py
Lightweight Telegram notification helper for operators.

Requires TELEGRAM_BOT_TOKEN in Django settings.
Messages are sent via the Bot API sendMessage endpoint.
"""
import logging
import urllib.request
import urllib.parse
import json

from django.conf import settings

logger = logging.getLogger(__name__)


def _bot_token():
    return getattr(settings, 'TELEGRAM_BOT_TOKEN', '')


def send_telegram_message(chat_id: str, text: str) -> bool:
    """
    Send a plain-text message to a Telegram chat.
    Returns True on success, False on any error (never raises).
    """
    token = _bot_token()
    if not token or not chat_id:
        return False

    url = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = json.dumps({
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as exc:
        logger.warning('Telegram notification failed (chat_id=%s): %s', chat_id, exc)
        return False


# ── Operator notification helpers ─────────────────────────────────────────────

def notify_operator_new_booking(booking):
    """Notify operator on Telegram when a new booking is made."""
    op = booking.tour.operator
    if not op.telegram_chat_id:
        return
    text = (
        f'\U0001f4cb <b>New booking</b>\n\n'
        f'Tour: {booking.tour.title}\n'
        f'Ref:  <code>{booking.reference}</code>\n'
        f'Guest: {booking.first_name} {booking.last_name}\n'
        f'Departure: {booking.departure_date}\n'
        f'Pax: {booking.adults}A'
        + (f' {booking.children}C' if booking.children else '')
        + (f' {booking.infants}I' if booking.infants else '')
        + f'\nTotal: {booking.total_price} {booking.tour.currency}'
    )
    send_telegram_message(op.telegram_chat_id, text)


def notify_operator_cancellation(booking):
    """Notify operator on Telegram when a booking is cancelled."""
    op = booking.tour.operator
    if not op.telegram_chat_id:
        return
    text = (
        f'\u274c <b>Booking cancelled</b>\n\n'
        f'Tour: {booking.tour.title}\n'
        f'Ref:  <code>{booking.reference}</code>\n'
        f'Guest: {booking.first_name} {booking.last_name}\n'
        f'Departure: {booking.departure_date}'
    )
    send_telegram_message(op.telegram_chat_id, text)


def notify_operator_balance_paid(booking):
    """Notify operator on Telegram when outstanding balance is paid."""
    op = booking.tour.operator
    if not op.telegram_chat_id:
        return
    text = (
        f'\u2705 <b>Balance received</b>\n\n'
        f'Tour: {booking.tour.title}\n'
        f'Ref:  <code>{booking.reference}</code>\n'
        f'Guest: {booking.first_name} {booking.last_name}\n'
        f'Amount: {booking.total_price} {booking.tour.currency}'
    )
    send_telegram_message(op.telegram_chat_id, text)


def notify_operator_waitlist_entry(tour, entry, departure=None):
    """Notify operator on Telegram when someone joins the waitlist."""
    op = tour.operator
    if not op.telegram_chat_id:
        return
    dep_str = (
        departure.start_date.strftime('%d %b %Y') if departure
        else (entry.departure_label or 'selected date')
    )
    text = (
        f'\u23f3 <b>New waitlist entry</b>\n\n'
        f'Tour: {tour.title}\n'
        f'Departure: {dep_str}\n'
        f'Traveller: {entry.name or entry.email} ({entry.email})'
    )
    send_telegram_message(op.telegram_chat_id, text)
