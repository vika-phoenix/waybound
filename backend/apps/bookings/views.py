"""
apps/bookings/views.py

Endpoints:
  GET  /api/v1/bookings/                 — tourist: own bookings
  POST /api/v1/bookings/                 — tourist: create booking
  GET  /api/v1/bookings/<pk>/            — tourist: booking detail
  PATCH /api/v1/bookings/<pk>/cancel/    — tourist: cancel booking

  GET  /api/v1/bookings/operator/        — operator: bookings for own tours
  PATCH /api/v1/bookings/<pk>/confirm/   — operator: confirm a booking

  POST /api/v1/bookings/enquiries/       — create private tour enquiry
  GET  /api/v1/bookings/enquiries/       — operator: see enquiries for own tours
"""
import zoneinfo
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings as django_settings

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .models import Booking, EnquiryMessage, EnquiryReply
from .serializers import (
    BookingCreateSerializer,
    BookingDetailSerializer,
    OperatorBookingSerializer,
    EnquiryCreateSerializer,
    EnquiryDetailSerializer,
)


# ── Email helpers ─────────────────────────────────────────────────────────────

def _site_url():
    return getattr(django_settings, 'FRONTEND_URL', 'http://localhost:8080')

def _from_email():
    return getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@waybound.com')

def _tourist_email(enquiry):
    """Best available email for the tourist — form field first, sender account second."""
    return enquiry.email or (enquiry.sender.email if enquiry.sender else '')

def _html_email(title, body_html, cta_label, cta_url):
    """Minimal branded HTML email with a single CTA button."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f5f9;font-family:'Helvetica Neue',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f5f9;padding:40px 16px">
    <tr><td>
      <table width="600" cellpadding="0" cellspacing="0" align="center"
             style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;
                    overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,.10)">
        <tr><td style="background:#1a2535;padding:22px 32px">
          <span style="font-family:Georgia,serif;font-size:22px;color:#4fa8d4;font-weight:400;letter-spacing:.03em">waybound</span>
        </td></tr>
        <tr><td style="padding:32px 32px 20px">
          <h2 style="margin:0 0 16px;font-size:20px;color:#0d1f2d;font-weight:700;line-height:1.3">{title}</h2>
          {body_html}
        </td></tr>
        <tr><td style="padding:4px 32px 36px;text-align:center">
          <a href="{cta_url}"
             style="display:inline-block;background:#4fa8d4;color:#0d1f2d;text-decoration:none;
                    font-weight:700;font-size:15px;padding:14px 36px;border-radius:8px;
                    font-family:'Helvetica Neue',Arial,sans-serif">{cta_label} &rarr;</a>
        </td></tr>
        <tr><td style="background:#f4f8fb;padding:18px 32px;border-top:1px solid #e0eaf0">
          <p style="margin:0;font-size:12px;color:#8a9aaa;line-height:1.65">
            This is an automated notification from Waybound.
            <strong style="color:#607080">Please do not reply to this email</strong> —
            replies are not monitored. Use the button above to continue your conversation on Waybound.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ── Email notification senders ────────────────────────────────────────────────

def _booking_rows_html(booking):
    """Shared detail table used across booking emails."""
    dep = str(booking.departure_date) if booking.departure_date else 'TBC'
    pax = f'{booking.adults} adult' + ('s' if booking.adults != 1 else '')
    if booking.children:
        pax += f', {booking.children} child' + ('ren' if booking.children != 1 else '')
    if booking.infants:
        pax += f', {booking.infants} infant' + ('s' if booking.infants != 1 else '')
    rows = [
        ('Booking ref', booking.reference),
        ('Tour',        booking.tour.title),
        ('Departure',   dep),
        ('Travellers',  pax),
        ('Total',       f'{booking.currency} {booking.total_price:,.0f}'),
    ]
    html = '<table style="width:100%;border-collapse:collapse;margin-bottom:16px;font-size:13px">'
    for i, (label, val) in enumerate(rows):
        bg = '#f4f8fb' if i % 2 == 0 else '#ffffff'
        html += (f'<tr style="background:{bg}"><td style="padding:8px 12px;font-weight:700;'
                 f'color:#607080;width:40%">{label}</td>'
                 f'<td style="padding:8px 12px;color:#0d1f2d">{val}</td></tr>')
    return html + '</table>'


def send_booking_created_emails(booking):
    """Tourist receipt + operator alert on new booking (status=pending)."""
    site    = _site_url()
    from_em = _from_email()
    title   = booking.tour.title
    name    = (booking.first_name or '').strip() or 'Traveller'
    rows    = _booking_rows_html(booking)

    tourist_body = (
        f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">Hi {name},</p>'
        f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
        f'We\'ve received your booking request for <strong>{title}</strong>. '
        f'Please complete payment to confirm your spot.</p>{rows}'
    )
    try:
        send_mail(
            subject=f'Booking received: {title} — complete your payment',
            message=f'Hi {name},\n\nBooking received for "{title}".\nRef: {booking.reference}\n\nComplete payment: {site}/my-bookings.html',
            from_email=from_em,
            html_message=_html_email(f'Booking received: {title}', tourist_body,
                                      'View my bookings', f'{site}/my-bookings.html'),
            recipient_list=[booking.email],
            fail_silently=True,
        )
    except Exception:
        pass

    op_body = (
        f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
        f'New booking request for <strong>{title}</strong> from <strong>{name}</strong>. '
        f'Payment is pending.</p>{rows}'
    )
    try:
        send_mail(
            subject=f'New booking request: {title}',
            message=f'New booking for "{title}" from {name}.\nRef: {booking.reference}\n\nDashboard: {site}/operator-dashboard.html#bookings',
            from_email=from_em,
            html_message=_html_email(f'New booking: {title}', op_body,
                                      'View in dashboard', f'{site}/operator-dashboard.html#bookings'),
            recipient_list=[booking.tour.operator.email],
            fail_silently=True,
        )
    except Exception:
        pass


def send_booking_confirmed_emails(booking):
    """Tourist confirmation email when operator confirms."""
    site    = _site_url()
    from_em = _from_email()
    title   = booking.tour.title
    name    = (booking.first_name or '').strip() or 'Traveller'
    rows    = _booking_rows_html(booking)

    tourist_body = (
        f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">Hi {name},</p>'
        f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
        f'Great news — your booking for <strong>{title}</strong> is confirmed! '
        f'The operator will be in touch with further details closer to your departure.</p>'
        f'{rows}'
        f'<p style="margin:12px 0 0;font-size:13px;color:#607080;line-height:1.65">'
        f'Your reference is <strong>{booking.reference}</strong> — keep this handy for your guide.</p>'
    )
    try:
        send_mail(
            subject=f'\u2713 Booking confirmed: {title}',
            message=f'Hi {name},\n\nYour booking for "{title}" is confirmed!\nRef: {booking.reference}\n\nView: {site}/my-bookings.html',
            from_email=from_em,
            html_message=_html_email(f'\u2713 Confirmed: {title}', tourist_body,
                                      'View my bookings', f'{site}/my-bookings.html'),
            recipient_list=[booking.email],
            fail_silently=True,
        )
    except Exception:
        pass


def send_booking_cancelled_emails(booking, cancelled_by='tourist', reason=''):
    """Cancellation notification to the other party.
    cancelled_by: 'tourist' | 'operator' | 'operator_timeout' | 'system_no_deposit' | 'system_past_departure'
    """
    site    = _site_url()
    from_em = _from_email()
    title   = booking.tour.title
    name    = (booking.first_name or '').strip() or 'Traveller'
    rows    = _booking_rows_html(booking)

    # Ghost booking — tourist never paid, no email needed
    if cancelled_by == 'system_no_deposit':
        return

    # Tour date passed with booking still pending — notify tourist of full refund
    if cancelled_by == 'system_past_departure':
        body = (
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">Hi {name},</p>'
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
            f'Your booking for <strong>{title}</strong> was never confirmed by the operator '
            f'and the departure date has now passed. Your booking has been automatically cancelled '
            f'and your deposit will be fully refunded within 5–10 business days.</p>{rows}'
            f'<p style="margin:12px 0 0;font-size:13px;color:#607080">We apologise for the inconvenience. '
            f'Please <a href="{site}/adventures.html" style="color:#4fa8d4">browse other tours</a> or '
            f'contact support if you have questions.</p>'
        )
        try:
            send_mail(
                subject=f'Booking auto-cancelled (departure passed): {title}',
                message=f'Hi {name},\n\nYour booking for "{title}" was never confirmed and the departure date has passed. It has been auto-cancelled and your deposit will be fully refunded.',
                from_email=from_em,
                html_message=_html_email('Booking auto-cancelled', body, 'Browse tours', f'{site}/adventures.html'),
                recipient_list=[booking.email],
                fail_silently=True,
            )
        except Exception:
            pass
        return

    # Operator timed out — notify tourist (refund) + operator (missed booking)
    if cancelled_by == 'operator_timeout':
        body = (
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">Hi {name},</p>'
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
            f'Unfortunately, your booking for <strong>{title}</strong> was not confirmed by the operator '
            f'within the required 48 hours. It has been automatically cancelled and your deposit '
            f'will be fully refunded within 5–10 business days.</p>{rows}'
            f'<p style="margin:12px 0 0;font-size:13px;color:#607080">We\'re sorry for the inconvenience. '
            f'Please <a href="{site}/adventures.html" style="color:#4fa8d4">browse other tours</a> or contact support.</p>'
        )
        try:
            send_mail(
                subject=f'Your booking was not confirmed: {title}',
                message=f'Hi {name},\n\nYour booking for "{title}" was not confirmed in time and has been automatically cancelled. Your deposit will be refunded.',
                from_email=from_em,
                html_message=_html_email('Booking not confirmed', body, 'Browse tours', f'{site}/adventures.html'),
                recipient_list=[booking.email],
                fail_silently=True,
            )
        except Exception:
            pass
        # Notify operator they missed the confirmation window
        op_body = (
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
            f'A booking for <strong>{title}</strong> by <strong>{name}</strong> was automatically '
            f'cancelled because it was not confirmed within 48 hours.</p>{rows}'
            f'<p style="margin:12px 0 0;font-size:13px;color:#607080">'
            f'Please confirm bookings promptly to avoid losing customers.</p>'
        )
        try:
            send_mail(
                subject=f'Booking auto-cancelled (not confirmed in time): {title}',
                message=f'Booking for "{title}" by {name} was auto-cancelled because it was not confirmed within 48 hours.\nRef: {booking.reference}',
                from_email=from_em,
                html_message=_html_email('Missed booking', op_body,
                                          'View bookings', f'{site}/operator-dashboard.html#bookings'),
                recipient_list=[booking.tour.operator.email],
                fail_silently=True,
            )
        except Exception:
            pass
        return

    if cancelled_by == 'tourist':
        op_body = (
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
            f'The booking for <strong>{title}</strong> by <strong>{name}</strong> '
            f'has been cancelled by the traveller.</p>{rows}'
        )
        try:
            send_mail(
                subject=f'Booking cancelled: {title}',
                message=f'Booking for "{title}" by {name} was cancelled.\nRef: {booking.reference}',
                from_email=from_em,
                html_message=_html_email('Booking cancelled', op_body,
                                          'View bookings', f'{site}/operator-dashboard.html#bookings'),
                recipient_list=[booking.tour.operator.email],
                fail_silently=True,
            )
        except Exception:
            pass
    else:
        reason_html = (
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
            f'<strong>Message from operator:</strong> {reason}</p>'
        ) if reason else ''
        tourist_body = (
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">Hi {name},</p>'
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
            f'Your booking for <strong>{title}</strong> has been cancelled by the operator. '
            f'If a deposit was paid, a refund will be processed within 5–10 business days.</p>'
            f'{reason_html}{rows}'
            f'<p style="margin:14px 0 0;font-size:13px;color:#555;line-height:1.6">'
            f'If you have any questions or concerns, please don\'t hesitate to '
            f'<a href="{site}/contact.html" style="color:#2a7ae2">contact our support team</a>.</p>'
        )
        try:
            send_mail(
                subject=f'Your booking has been cancelled: {title}',
                message=f'Hi {name},\n\nYour booking for "{title}" was cancelled by the operator.\nRef: {booking.reference}' + (f'\n\nMessage: {reason}' if reason else '') + f'\n\nIf you have any questions or concerns, please contact us at {site}/contact.html',
                from_email=from_em,
                html_message=_html_email('Booking cancelled', tourist_body,
                                          'Contact support', f'{site}/contact.html'),
                recipient_list=[booking.email],
                fail_silently=True,
            )
        except Exception:
            pass


# kept for backward-compat — now unused
def send_booking_notification(booking):
    pass


def send_enquiry_notifications(enquiry):
    """Email operator on new enquiry; confirmation to tourist."""
    site      = _site_url()
    from_em   = _from_email()
    title     = enquiry.tour.title
    name      = enquiry.name or 'A traveller'
    msg_preview = (enquiry.message or '(no message)')[:200]

    # ── Notify operator ──
    op_url  = f'{site}/operator-dashboard.html?tab=messages&open={enquiry.id}'
    op_body = (
        f'<p style="margin:0 0 12px;font-size:14px;color:#0d1f2d;line-height:1.65">'
        f'You have a new enquiry for <strong>{title}</strong>.</p>'
        f'<table style="width:100%;border-collapse:collapse;margin-bottom:16px">'
        f'<tr><td style="padding:8px 12px;background:#f4f8fb;border-radius:6px 6px 0 0;'
        f'font-size:12px;font-weight:700;color:#607080;text-transform:uppercase;'
        f'letter-spacing:.05em">From</td>'
        f'<td style="padding:8px 12px;background:#f4f8fb;border-radius:6px 6px 0 0;'
        f'font-size:13px;color:#0d1f2d">{name}</td></tr>'
        f'<tr><td style="padding:8px 12px;border-top:1px solid #e0eaf0;font-size:12px;'
        f'font-weight:700;color:#607080;text-transform:uppercase;letter-spacing:.05em">Message</td>'
        f'<td style="padding:8px 12px;border-top:1px solid #e0eaf0;font-size:13px;'
        f'color:#0d1f2d;font-style:italic">{msg_preview}</td></tr>'
        f'</table>'
    )
    try:
        send_mail(
            subject=f'New enquiry: {title}',
            message=f'New enquiry for "{title}" from {name}.\n\nMessage: {msg_preview}\n\nReply on Waybound: {op_url}',
            from_email=from_em,
            html_message=_html_email(f'New enquiry for {title}', op_body, 'Reply on Waybound', op_url),
            recipient_list=[enquiry.tour.operator.email],
            fail_silently=True,
        )
    except Exception:
        pass

    # ── Confirm to tourist ──
    tourist_em = _tourist_email(enquiry)
    if tourist_em:
        tourist_url  = f'{site}/my-messages.html'
        tourist_body = (
            f'<p style="margin:0 0 12px;font-size:14px;color:#0d1f2d;line-height:1.65">'
            f'Hi {name},</p>'
            f'<p style="margin:0 0 16px;font-size:14px;color:#0d1f2d;line-height:1.65">'
            f'Thanks for your interest in <strong>{title}</strong>. '
            f'The operator will review your message and reply within 48 hours.</p>'
        )
        try:
            send_mail(
                subject=f'We received your enquiry for {title}',
                message=f'Hi {name},\n\nThanks for your interest in "{title}".\nThe operator will reply within 48 hours.\n\nView your messages: {tourist_url}',
                from_email=from_em,
                html_message=_html_email(f'Enquiry received: {title}', tourist_body, 'View your messages', tourist_url),
                recipient_list=[tourist_em],
                fail_silently=True,
            )
        except Exception:
            pass


def send_enquiry_reply_notification(enquiry):
    """Email tourist when operator posts a reply."""
    tourist_em = _tourist_email(enquiry)
    if not tourist_em:
        return
    site   = _site_url()
    title  = enquiry.tour.title
    name   = enquiry.name or 'there'
    reply_preview = (enquiry.operator_reply or '')[:300]
    url    = f'{site}/my-messages.html'
    body   = (
        f'<p style="margin:0 0 12px;font-size:14px;color:#0d1f2d;line-height:1.65">'
        f'Hi {name},</p>'
        f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
        f'The operator has replied to your enquiry about <strong>{title}</strong>:</p>'
        f'<blockquote style="margin:0 0 16px;padding:12px 18px;background:#f0faf4;'
        f'border-left:3px solid #2e9e5a;border-radius:0 8px 8px 0;'
        f'font-size:13px;color:#0d1f2d;line-height:1.65;font-style:italic">'
        f'{reply_preview}</blockquote>'
    )
    try:
        send_mail(
            subject=f'Reply to your enquiry: {title}',
            message=f'Hi {name},\n\nThe operator replied to your enquiry about "{title}":\n\n"{reply_preview}"\n\nView and reply: {url}',
            from_email=_from_email(),
            html_message=_html_email(f'Operator replied: {title}', body, 'View & reply on Waybound', url),
            recipient_list=[tourist_em],
            fail_silently=True,
        )
    except Exception:
        pass


def send_tourist_reply_notification(enquiry):
    """Email operator when tourist sends a follow-up message."""
    site     = _site_url()
    title    = enquiry.tour.title
    name     = enquiry.name or 'Tourist'
    op_url   = f'{site}/operator-dashboard.html?tab=messages&open={enquiry.id}'
    # Get last tourist reply body for preview
    last_reply = enquiry.replies.filter(is_operator=False).order_by('-created_at').first()
    preview  = (last_reply.body[:200] if last_reply else '')
    body     = (
        f'<p style="margin:0 0 12px;font-size:14px;color:#0d1f2d;line-height:1.65">'
        f'<strong>{name}</strong> has replied to the enquiry about <strong>{title}</strong>:</p>'
        f'<blockquote style="margin:0 0 16px;padding:12px 18px;background:#f4f8fb;'
        f'border-left:3px solid #4fa8d4;border-radius:0 8px 8px 0;'
        f'font-size:13px;color:#0d1f2d;line-height:1.65;font-style:italic">'
        f'{preview}</blockquote>'
    )
    try:
        send_mail(
            subject=f'Tourist replied: {title}',
            message=f'{name} replied to the enquiry about "{title}".\n\nMessage: {preview}\n\nView on Waybound: {op_url}',
            from_email=_from_email(),
            html_message=_html_email(f'New reply from {name}', body, 'View conversation', op_url),
            recipient_list=[enquiry.tour.operator.email],
            fail_silently=True,
        )
    except Exception:
        pass


# ── Tourist: own bookings ─────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def booking_list(request):
    """
    GET  — tourist sees their own bookings (all statuses)
    POST — tourist creates a new booking
    """
    if request.method == 'GET':
        qs = Booking.objects.filter(tourist=request.user).select_related(
            'tour__operator', 'departure'
        ).prefetch_related('tour__photos')

        # Optional status filter
        status_filter = request.GET.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        serializer = BookingDetailSerializer(qs, many=True, context={'request': request})
        return Response({'count': qs.count(), 'results': serializer.data})

    # POST — create booking
    serializer = BookingCreateSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    booking = serializer.save()

    # Set cooling-off window: 30 min if departure >7 days, 15 min if ≤7 days
    _now = timezone.now()
    if booking.departure_date:
        days_to_dep = (booking.departure_date - _now.date()).days
        _window_mins = 15 if days_to_dep <= 7 else 30
    else:
        _window_mins = 30
    booking.cooling_off_until = _now + timedelta(minutes=_window_mins)
    booking.save(update_fields=['cooling_off_until'])

    send_booking_created_emails(booking)
    try:
        from apps.tours.telegram import notify_operator_new_booking
        notify_operator_new_booking(booking)
    except Exception:
        pass
    return Response(
        BookingDetailSerializer(booking, context={'request': request}).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def booking_detail(request, pk):
    """GET /api/v1/bookings/<pk>/"""
    booking = get_object_or_404(Booking, pk=pk)

    # Tourist can only see their own; operator can see bookings for their tours
    user = request.user
    if booking.tourist != user and booking.tour.operator != user and not user.is_staff:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = BookingDetailSerializer(booking, context={'request': request})
    return Response(serializer.data)


PLATFORM_DEFAULT_CANCEL_POLICY = [
    {'days_before_min': 30, 'days_before_max': None, 'penalty_pct': 0,   'label': 'Full refund (30+ days)'},
    {'days_before_min': 14, 'days_before_max': 29,   'penalty_pct': 50,  'label': '50% refund (14–29 days)'},
    {'days_before_min': 0,  'days_before_max': 13,   'penalty_pct': 100, 'label': 'No refund (within 14 days)'},
]


def _tour_today(tour):
    """Return today's date in the tour's departure timezone."""
    tz_name = getattr(tour, 'timezone', '') or 'Europe/Moscow'
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except (KeyError, Exception):
        tz = zoneinfo.ZoneInfo('Europe/Moscow')
    return timezone.now().astimezone(tz).date()


def compute_dynamic_deposit_pct(booking):
    """
    Dynamic deposit: the higher of the tour's base deposit_pct or the applicable
    cancellation penalty_pct based on how far the departure date is.

    If the tourist books close to departure, they may already be in a high-penalty
    window, so the deposit should cover that penalty (protecting the operator).
    """
    base_pct = getattr(booking.tour, 'deposit_pct', 30) or 30

    if not booking.departure_date:
        return base_pct

    today = _tour_today(booking.tour)
    days_remaining = max(0, (booking.departure_date - today).days)
    snapshot = booking.cancel_policy_snapshot or PLATFORM_DEFAULT_CANCEL_POLICY

    penalty_pct = 0
    for tier in snapshot:
        mn = tier.get('days_before_min', 0)
        mx = tier.get('days_before_max')
        if days_remaining >= mn and (mx is None or days_remaining <= mx):
            penalty_pct = tier.get('penalty_pct', 0)
            break

    return max(base_pct, penalty_pct)


def _compute_refund(booking, cancelled_by='tourist'):
    """
    Returns (refund_amount, penalty_pct, tier_label) in tour currency.
    - operator/system cancel → always 100% refund of paid amount
    - tourist cancel → apply cancel_policy_snapshot based on days to departure
    - No policy or no departure_date → full refund
    """
    import logging as _log
    logger = _log.getLogger(__name__)

    total_paid = round(float(booking.deposit_paid) + float(booking.balance_paid), 2)

    if total_paid <= 0:
        return 0.0, 0, 'Nothing paid'

    if cancelled_by != 'tourist':
        # Operator or system cancels — full refund to tourist
        return total_paid, 0, 'Full refund (operator cancellation)'

    # ── 1. Cooling-off window (highest priority) ──────────────────────────────
    # Overrides all cancellation policy rules. Set at booking creation:
    # +30 min if departure >7 days away, +15 min if ≤7 days.
    from django.utils import timezone as _tz
    cooling_off = getattr(booking, 'cooling_off_until', None)
    if cooling_off and _tz.now() <= cooling_off:
        logger.info(
            'Refund calc: booking=%s — within cooling-off window (until %s), full refund',
            booking.reference, cooling_off,
        )
        return total_paid, 0, 'Full refund (cancelled within cooling-off window)'

    # ── 2. Penalty-free window after operator changes material tour details ───
    window_until = getattr(booking.tour, 'change_cancel_window_until', None)
    if window_until and _tz.now() <= window_until:
        return total_paid, 0, 'Full refund (operator changed tour details)'

    if not booking.departure_date:
        return total_paid, 0, 'Full refund (no departure date)'

    today = _tour_today(booking.tour)
    days_remaining = (booking.departure_date - today).days

    snapshot = booking.cancel_policy_snapshot or []
    if not snapshot:
        snapshot = PLATFORM_DEFAULT_CANCEL_POLICY

    # Find matching tier: days_before_min <= days_remaining <= days_before_max (null=∞)
    penalty_pct = 0
    tier_label  = 'Full refund'
    for tier in snapshot:
        mn = tier.get('days_before_min', 0)
        mx = tier.get('days_before_max')
        if days_remaining >= mn and (mx is None or days_remaining <= mx):
            penalty_pct = tier.get('penalty_pct', 0)
            tier_label  = tier.get('label') or f'{penalty_pct}% cancellation fee'
            break

    # Penalty is calculated on the TOTAL booking value (industry standard),
    # not on the amount paid.  Refund = what was paid minus penalty, floored at 0.
    total_price = round(float(booking.total_price), 2)
    penalty_abs = round(total_price * penalty_pct / 100, 2)
    refund      = max(0.0, round(total_paid - penalty_abs, 2))
    logger.info(
        'Refund calc: booking=%s days_remaining=%d penalty=%d%% total_price=%.2f paid=%.2f penalty_abs=%.2f refund=%.2f',
        booking.reference, days_remaining, penalty_pct, total_price, total_paid, penalty_abs, refund,
    )
    return refund, penalty_pct, tier_label


def _issue_yookassa_refund(booking, refund_amount_tour_currency):
    """
    Create a YooKassa refund for the given amount (in tour currency).
    Converts to RUB via CBR. Returns (success: bool, message: str).
    """
    if booking.payment_method not in ('yookassa', 'sbp'):
        return False, 'bank'

    payment_id = booking.yookassa_payment_id
    if not payment_id:
        return False, 'no_payment_id'

    try:
        from apps.payments.views import convert_to_rub
        import yookassa, uuid as _uuid
        from django.conf import settings as _settings
        yookassa.Configuration.account_id = _settings.YOOKASSA_SHOP_ID
        yookassa.Configuration.secret_key = _settings.YOOKASSA_SECRET_KEY

        currency = booking.currency or 'RUB'
        rub_amount, _ = convert_to_rub(refund_amount_tour_currency, currency)

        yookassa.Refund.create({
            'payment_id': payment_id,
            'amount': {'value': f'{rub_amount:.2f}', 'currency': 'RUB'},
            'description': f'Refund for booking {booking.reference}',
        }, str(_uuid.uuid4()))
        return True, 'issued'
    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).error('YooKassa refund error for %s: %s', booking.reference, exc)
        return False, 'error'


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def booking_cancel_preview(request, pk):
    """GET /api/v1/bookings/<pk>/cancel-preview/  — preview refund without cancelling."""
    booking = get_object_or_404(Booking, pk=pk)

    is_tourist  = booking.tourist == request.user
    is_operator = booking.tour.operator == request.user or request.user.is_staff
    if not is_tourist and not is_operator:
        return Response({'detail': 'Not your booking.'}, status=status.HTTP_403_FORBIDDEN)

    if booking.status not in [Booking.Status.PENDING, Booking.Status.CONFIRMED]:
        return Response({'detail': f'Booking is {booking.status}.'}, status=status.HTTP_400_BAD_REQUEST)

    cancelled_by = 'tourist' if is_tourist else 'operator'
    refund_amount, penalty_pct, tier_label = _compute_refund(booking, cancelled_by)

    total_paid = round(float(booking.deposit_paid) + float(booking.balance_paid), 2)
    currency   = booking.currency or 'RUB'

    total_price    = round(float(booking.total_price), 2)
    penalty_amount = max(0.0, round(total_paid - refund_amount, 2))

    resp = {
        'total_paid':      total_paid,
        'total_price':     total_price,
        'refund_amount':   refund_amount,
        'penalty_amount':  penalty_amount,
        'penalty_pct':     penalty_pct,
        'tier_label':      tier_label,
        'currency':        currency,
        'payment_method':  booking.payment_method,
    }

    # For YooKassa / SBP — the actual refund is always issued in RUB,
    # so also return the RUB equivalents so the frontend can display correctly.
    if booking.payment_method in ('yookassa', 'sbp') and currency != 'RUB':
        try:
            from apps.payments.views import convert_to_rub
            refund_rub, rate    = convert_to_rub(refund_amount, currency)
            total_paid_rub, _   = convert_to_rub(total_paid,    currency)
            resp['refund_rub']      = refund_rub
            resp['total_paid_rub']  = total_paid_rub
            resp['exchange_rate']   = rate
        except Exception:
            pass   # skip RUB fields if CBR unreachable — frontend falls back to tour currency

    return Response(resp)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def booking_cancel(request, pk):
    """PATCH /api/v1/bookings/<pk>/cancel/  — tourist or operator."""
    booking = get_object_or_404(Booking, pk=pk)

    is_tourist  = booking.tourist == request.user
    is_operator = booking.tour.operator == request.user or request.user.is_staff
    if not is_tourist and not is_operator:
        return Response({'detail': 'Not your booking.'}, status=status.HTTP_403_FORBIDDEN)

    if booking.status not in [Booking.Status.PENDING, Booking.Status.CONFIRMED]:
        return Response({'detail': f'Cannot cancel a {booking.status} booking.'},
                        status=status.HTTP_400_BAD_REQUEST)

    cancelled_by = 'tourist' if is_tourist else 'operator'

    # Compute refund before changing status
    refund_amount, penalty_pct, tier_label = _compute_refund(booking, cancelled_by)

    booking.status       = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()

    if refund_amount > 0:
        booking.refund_amount = refund_amount
        ok, msg = _issue_yookassa_refund(booking, refund_amount)
        if ok:
            booking.refund_status = 'issued'
        elif msg == 'bank':
            booking.refund_status = 'manual'
        else:
            booking.refund_status = 'pending'   # failed — handle manually
    else:
        booking.refund_status = 'none'

    booking.save(update_fields=['status', 'cancelled_at', 'refund_amount', 'refund_status'])

    # Free up the departure spot
    if booking.departure:
        booking.departure.spots_left = min(
            booking.departure.spots_total,
            booking.departure.spots_left + booking.adults + booking.children,
        )
        booking.departure.save(update_fields=['spots_left'])
        # Notify anyone on the waitlist for this departure
        if booking.departure.spots_left > 0:
            try:
                from apps.tours.emails import notify_waitlist_for_departure
                notify_waitlist_for_departure(booking.departure)
            except Exception:
                pass

    reason = (request.data.get('reason') or '').strip()
    send_booking_cancelled_emails(booking, cancelled_by=cancelled_by, reason=reason)
    if cancelled_by == 'tourist':
        try:
            from apps.tours.telegram import notify_operator_cancellation
            notify_operator_cancellation(booking)
        except Exception:
            pass

    # If operator provided a reason, surface it in the messaging inbox
    if reason and cancelled_by == 'operator' and booking.tourist:
        from .models import EnquiryMessage, EnquiryReply
        thread = EnquiryMessage.objects.filter(
            tour=booking.tour, sender=booking.tourist,
        ).order_by('-created_at').first()
        if thread:
            EnquiryReply.objects.create(
                enquiry    = thread,
                sender     = request.user,
                is_operator= True,
                body       = f'Your booking ({booking.reference}) has been cancelled.\n\n{reason}',
            )

    return Response(BookingDetailSerializer(booking, context={'request': request}).data)


# ── Operator: bookings for their tours ───────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def operator_booking_list(request):
    """
    GET /api/v1/bookings/operator/
    Returns all bookings for tours owned by the authenticated operator.
    """
    if request.user.role != 'operator' and not request.user.is_staff:
        return Response({'detail': 'Operator account required.'}, status=status.HTTP_403_FORBIDDEN)

    from django.db.models import Exists, OuterRef, Subquery, IntegerField
    from .models import EnquiryMessage

    qs = Booking.objects.filter(
        tour__operator=request.user
    ).select_related('tour', 'departure').order_by('-created_at')

    # Filters
    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    tour_slug = request.GET.get('tour')
    if tour_slug:
        qs = qs.filter(tour__slug=tour_slug)

    # Annotate each booking with messaging info (single SQL, no N+1)
    enq_base = EnquiryMessage.objects.filter(
        tour=OuterRef('tour'), sender=OuterRef('tourist'),
    )
    qs = qs.annotate(
        _enquiry_id=Subquery(
            enq_base.order_by('-created_at').values('id')[:1],
            output_field=IntegerField(),
        ),
        _msg_unread=Exists(
            enq_base.filter(read_by_operator=False),
        ),
    )

    serializer = OperatorBookingSerializer(qs, many=True, context={'request': request})
    return Response({'count': qs.count(), 'results': serializer.data})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def booking_confirm(request, pk):
    """PATCH /api/v1/bookings/<pk>/confirm/  — operator confirms a booking."""
    booking = get_object_or_404(Booking, pk=pk)

    if booking.tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your tour.'}, status=status.HTTP_403_FORBIDDEN)

    if booking.status != Booking.Status.PENDING:
        return Response({'detail': 'Only pending bookings can be confirmed.'},
                        status=status.HTTP_400_BAD_REQUEST)

    booking.status       = Booking.Status.CONFIRMED
    booking.confirmed_at = timezone.now()
    booking.save(update_fields=['status', 'confirmed_at'])

    # Decrement departure spots
    if booking.departure:
        booked = booking.adults + booking.children
        booking.departure.spots_left = max(0, booking.departure.spots_left - booked)
        booking.departure.save(update_fields=['spots_left'])

    send_booking_confirmed_emails(booking)

    return Response(OperatorBookingSerializer(booking, context={'request': request}).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def operator_message(request, pk):
    """
    POST /api/v1/bookings/<pk>/message/
    Operator sends a message to the tourist about a booking.
    Body: { message: str }

    If an enquiry thread already exists for this tour + tourist, appends as a reply.
    Either way sends an email to the tourist.
    """
    booking = get_object_or_404(Booking, pk=pk)

    is_operator = booking.tour.operator == request.user or request.user.is_staff
    is_tourist  = booking.tourist == request.user

    if not is_operator and not is_tourist:
        return Response({'detail': 'Not your booking.'}, status=status.HTTP_403_FORBIDDEN)

    body = (request.data.get('message') or request.data.get('body') or '').strip()
    if not body:
        return Response({'detail': 'message is required.'}, status=status.HTTP_400_BAD_REQUEST)

    tourist  = booking.tourist
    operator = booking.tour.operator

    # ── Add to inbox thread ───────────────────────────────────────────────────
    if tourist:
        from .models import EnquiryMessage, EnquiryReply
        thread = EnquiryMessage.objects.filter(
            tour=booking.tour, sender=tourist,
        ).order_by('-created_at').first()

        if not thread:
            thread = EnquiryMessage.objects.create(
                tour    = booking.tour,
                sender  = tourist,
                name    = f'{tourist.first_name} {tourist.last_name}'.strip() or tourist.email,
                email   = tourist.email,
                message = f'[Booking enquiry — {booking.reference}]',
            )

        EnquiryReply.objects.create(
            enquiry     = thread,
            sender      = request.user,
            is_operator = is_operator,
            body        = body,
        )
        if is_operator:
            thread.operator_reply = body
            thread.replied_at     = timezone.now()
            thread.save(update_fields=['operator_reply', 'replied_at'])
        else:
            thread.read_by_operator = False
            thread.save(update_fields=['read_by_operator'])

    # ── Send email notification ───────────────────────────────────────────────
    site    = _site_url()
    from_em = _from_email()
    title   = booking.tour.title

    if is_operator:
        # Operator → notify tourist
        name    = (booking.first_name or '').strip() or 'Traveller'
        op_name = f'{request.user.first_name} {request.user.last_name}'.strip() or request.user.email
        recipient = booking.email
        email_subject = f'Message from your tour operator — {title}'
        email_body = (
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">Hi {name},</p>'
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
            f'You have a message from <strong>{op_name}</strong> regarding your booking '
            f'<strong>{booking.reference}</strong> — {title}.</p>'
            f'<div style="background:#f4f9fc;border-left:3px solid #4fa8d4;border-radius:0 8px 8px 0;'
            f'padding:12px 16px;margin:0 0 16px;font-size:14px;color:#0d1f2d;line-height:1.7">'
            f'{body}</div>'
        )
        view_link = f'{site}/my-messages.html'
        link_label = 'View in messages'
    else:
        # Tourist → notify operator
        tourist_name = f'{tourist.first_name} {tourist.last_name}'.strip() or tourist.email if tourist else booking.email
        recipient = operator.email
        email_subject = f'Message from traveller — {booking.reference}'
        email_body = (
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
            f'Hi, you have a message from <strong>{tourist_name}</strong> regarding booking '
            f'<strong>{booking.reference}</strong> — {title}.</p>'
            f'<div style="background:#f4f9fc;border-left:3px solid #4fa8d4;border-radius:0 8px 8px 0;'
            f'padding:12px 16px;margin:0 0 16px;font-size:14px;color:#0d1f2d;line-height:1.7">'
            f'{body}</div>'
        )
        view_link = f'{site}/operator-dashboard.html'
        link_label = 'View in dashboard'

    try:
        from django.core.mail import send_mail
        send_mail(
            subject        = email_subject,
            message        = body,
            from_email     = from_em,
            html_message   = _html_email(email_subject, tourist_body, link_label, view_link),
            recipient_list = [recipient],
            fail_silently  = True,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error('operator_message email error: %s', exc)

    return Response({'status': 'sent'})


# ── Private tour enquiries ────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def enquiry_list(request):
    """
    GET  — operator sees enquiries for their tours (auth required, operator role)
    POST — anyone can submit an enquiry (AllowAny)
    """
    if request.method == 'POST':
        serializer = EnquiryCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        enquiry = serializer.save()
        send_enquiry_notifications(enquiry)
        return Response(
            EnquiryDetailSerializer(enquiry).data,
            status=status.HTTP_201_CREATED,
        )

    # GET — operator only
    if not request.user.is_authenticated:
        return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
    if request.user.role != 'operator' and not request.user.is_staff:
        return Response({'detail': 'Operator account required.'}, status=status.HTTP_403_FORBIDDEN)

    qs = EnquiryMessage.objects.filter(
        tour__operator=request.user
    ).select_related('tour').order_by('-created_at')

    unread = request.GET.get('unread')
    if unread == '1':
        qs = qs.filter(read_by_operator=False)

    serializer = EnquiryDetailSerializer(qs, many=True)
    return Response({'count': qs.count(), 'results': serializer.data})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def enquiry_mark_read(request, pk):
    """PATCH /api/v1/bookings/enquiries/<pk>/read/ — operator marks enquiry as read."""
    enquiry = get_object_or_404(EnquiryMessage, pk=pk)
    if enquiry.tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your tour.'}, status=status.HTTP_403_FORBIDDEN)
    enquiry.read_by_operator = True
    enquiry.save(update_fields=['read_by_operator'])
    return Response({'id': pk, 'read_by_operator': True})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def enquiry_reply(request, pk):
    """PATCH /api/v1/bookings/enquiries/<pk>/reply/ — operator adds a reply."""
    enquiry = get_object_or_404(EnquiryMessage, pk=pk)
    if enquiry.tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your tour.'}, status=status.HTTP_403_FORBIDDEN)
    reply = request.data.get('reply', '').strip()
    if not reply:
        return Response({'detail': 'Reply text required.'}, status=status.HTTP_400_BAD_REQUEST)
    # Create threaded reply
    EnquiryReply.objects.create(
        enquiry=enquiry, sender=request.user, is_operator=True, body=reply
    )
    # Keep legacy fields in sync
    enquiry.operator_reply = reply
    enquiry.read_by_operator = True
    enquiry.replied_at = timezone.now()
    enquiry.save(update_fields=['operator_reply', 'read_by_operator', 'replied_at'])
    send_enquiry_reply_notification(enquiry)
    return Response(EnquiryDetailSerializer(enquiry).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def enquiry_tourist_reply(request, pk):
    """POST /api/v1/bookings/enquiries/<pk>/tourist-reply/ — tourist follow-up message."""
    enquiry = get_object_or_404(EnquiryMessage, pk=pk)
    if enquiry.sender != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your enquiry.'}, status=status.HTTP_403_FORBIDDEN)
    body = request.data.get('reply', '').strip()
    if not body:
        return Response({'detail': 'Reply text required.'}, status=status.HTTP_400_BAD_REQUEST)
    # If old-style operator_reply exists with no EnquiryReply record, migrate it first
    if enquiry.operator_reply and not enquiry.replies.filter(is_operator=True).exists():
        EnquiryReply.objects.create(
            enquiry=enquiry,
            sender=enquiry.tour.operator,
            is_operator=True,
            body=enquiry.operator_reply,
        )
    # Create tourist's follow-up
    EnquiryReply.objects.create(
        enquiry=enquiry, sender=request.user, is_operator=False, body=body
    )
    # Mark unread for operator
    enquiry.read_by_operator = False
    enquiry.save(update_fields=['read_by_operator'])
    send_tourist_reply_notification(enquiry)
    return Response(EnquiryDetailSerializer(enquiry).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_enquiries(request):
    """GET /api/v1/bookings/my-enquiries/ — tourist sees their own sent enquiries."""
    qs = EnquiryMessage.objects.filter(
        sender=request.user
    ).select_related('tour').order_by('-created_at')
    serializer = EnquiryDetailSerializer(qs, many=True)
    return Response({'count': qs.count(), 'results': serializer.data})
