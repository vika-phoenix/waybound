"""
apps/tours/emails.py
Notification emails sent when operators make material changes to tours,
and when waitlisted tourists should be notified of available spots.
"""
import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

# Fields considered "material" — changes trigger tourist notification.
MATERIAL_FIELDS = {
    'price_adult':    'Base price per adult',
    'price_child':    'Base price per child',
    'cancel_policy':  'Cancellation policy',
    'extras':         'Optional add-ons / services',
    'stays':          'Accommodation / room options',
    'meeting_point':  'Meeting point / start location',
    'meeting_time':   'Meeting time',
    'destination':    'Tour destination',
}


def _site_url():
    return getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')


def _cancel_window_hours(tour) -> int:
    """Return penalty-free cancel window in hours based on nearest upcoming departure."""
    from django.utils import timezone
    today = timezone.now().date()
    nearest = tour.departures.filter(
        start_date__gte=today,
        status__in=['open', 'guaranteed'],
    ).order_by('start_date').first()
    if not nearest:
        return 48
    days_until = (nearest.start_date - today).days
    if days_until > 30:
        return 72
    elif days_until > 7:
        return 48
    else:
        return 24


def _describe_changes(changed_fields: list) -> str:
    lines = []
    for f in changed_fields:
        label = MATERIAL_FIELDS.get(f, f.replace('_', ' ').title())
        lines.append(f'  • {label}')
    return '\n'.join(lines)


def notify_tourists_of_tour_change(tour, changed_fields: list) -> int:
    """
    Email all tourists with active bookings on `tour` when material fields change.
    Includes a penalty-free cancel window based on departure proximity.
    Sets tour.change_cancel_window_until so cancellations within the window
    are actually refunded in full by _compute_refund.
    Returns number of emails sent.
    """
    from apps.bookings.models import Booking
    from django.utils import timezone as tz

    # Stamp the penalty-free window on the tour before sending emails
    window_hours = _cancel_window_hours(tour)
    tour.change_cancel_window_until = tz.now() + tz.timedelta(hours=window_hours)
    tour.save(update_fields=['change_cancel_window_until'])

    active_bookings = Booking.objects.filter(
        tour=tour,
        status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
    ).select_related('tourist')

    if not active_bookings.exists():
        return 0

    change_summary = _describe_changes(changed_fields)
    window_hours   = _cancel_window_hours(tour)
    from_email     = settings.DEFAULT_FROM_EMAIL
    site           = _site_url()
    sent           = 0
    seen_emails: set = set()

    for booking in active_bookings:
        recipient = booking.email
        if not recipient or recipient in seen_emails:
            continue
        seen_emails.add(recipient)

        name    = (booking.first_name or '').strip() or 'Traveller'
        subject = f'Update to your booking — {tour.title}'
        body    = (
            f'Hi {name},\n\n'
            f'The operator has made changes to the tour you have booked:\n\n'
            f'  Tour:         {tour.title}\n'
            f'  Booking ref:  {booking.reference}\n'
            f'  Departure:    {booking.departure_date}\n\n'
            f'The following details were updated:\n'
            f'{change_summary}\n\n'
            f'Your original booking terms (price and cancellation policy at the time\n'
            f'you booked) remain in effect. If you are not happy with these changes,\n'
            f'you may cancel your booking penalty-free within {window_hours} hours.\n\n'
            f'View your booking: {site}/my-bookings.html\n\n'
            f'If you have any questions, reply to this email or contact us at {from_email}.\n\n'
            f'Kind regards,\n'
            f'The Kavkazland Team'
        )
        try:
            send_mail(subject, body, from_email, [recipient], fail_silently=False)
            sent += 1
        except Exception as exc:
            logger.error('Failed to send tour-change email to %s: %s', recipient, exc)

    return sent


def notify_admin_of_tour_change(tour, changed_fields: list) -> None:
    """
    Email the site admin when an operator makes material changes to a live tour
    that has active bookings. Sent at the same time as tourist notifications.
    """
    admin_email = getattr(settings, 'ADMIN_NOTIFICATION_EMAIL', None) or getattr(settings, 'DEFAULT_FROM_EMAIL', None)
    if not admin_email:
        logger.warning('notify_admin_of_tour_change: no ADMIN_NOTIFICATION_EMAIL configured, skipping.')
        return

    from apps.bookings.models import Booking
    active_count = Booking.objects.filter(
        tour=tour,
        status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
    ).count()

    change_summary = _describe_changes(changed_fields)
    window_hours   = _cancel_window_hours(tour)
    operator_email = tour.operator.email or '—'

    subject = f'[Admin] Tour changed with active bookings — {tour.title}'
    body = (
        f'An operator has made material changes to a tour that has active bookings.\n\n'
        f'Tour:             {tour.title} (/{tour.slug})\n'
        f'Operator:         {tour.operator.full_name or tour.operator.email} ({operator_email})\n'
        f'Active bookings:  {active_count}\n'
        f'Tourist window:   {window_hours} hours penalty-free cancel granted\n\n'
        f'Fields changed:\n{change_summary}\n\n'
        f'Tourists with active bookings have been notified automatically.\n'
        f'Review in admin: /admin/tours/tour/?q={tour.slug}\n'
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [admin_email], fail_silently=True)
        logger.info('Admin notified of tour change for %s (%d fields)', tour.slug, len(changed_fields))
    except Exception as exc:
        logger.error('Failed to send admin tour-change email: %s', exc)


# ── Waitlist notifications ────────────────────────────────────────────────────

def send_waitlist_confirmation(tour, entry, departure=None):
    """
    Confirm to the tourist that they're on the waitlist.
    Also notify the operator so they can chase unpaid balances proactively.
    """
    from_email = settings.DEFAULT_FROM_EMAIL
    site       = _site_url()
    name       = (entry.name or 'Traveller').strip()
    dep_str    = (
        entry.departure_label
        or (departure.start_date.strftime('%-d %b %Y') if departure else 'your selected date')
    )

    # ── Tourist confirmation ──────────────────────────────────────────────────
    tourist_subject = f"You're on the waitlist — {tour.title}"
    tourist_body = (
        f'Hi {name},\n\n'
        f"You've been added to the waitlist for:\n\n"
        f'  Tour:       {tour.title}\n'
        f'  Departure:  {dep_str}\n\n'
        f"If a spot becomes available we'll notify you within 24–48 hours.\n"
        f'Spots are allocated on a first-come, first-served basis.\n\n'
        f'View tour: {site}/tour_detail_page.html?slug={tour.slug}\n\n'
        f'Kind regards,\nThe Kavkazland Team'
    )
    try:
        send_mail(tourist_subject, tourist_body, from_email, [entry.email], fail_silently=True)
    except Exception as exc:
        logger.error('Failed to send waitlist confirmation to %s: %s', entry.email, exc)

    # ── Operator notification ─────────────────────────────────────────────────
    op_email   = tour.operator.email
    op_subject = f'New waitlist entry — {tour.title}'
    op_body    = (
        f'Hi,\n\n'
        f'A traveller has joined the waitlist for your tour:\n\n'
        f'  Tour:       {tour.title}\n'
        f'  Departure:  {dep_str}\n'
        f'  Traveller:  {name} ({entry.email})\n\n'
        f'This indicates demand for this date. If you can free up a spot\n'
        f'(e.g. by following up on unpaid balances), the waitlisted traveller\n'
        f'will be notified automatically.\n\n'
        f'The Kavkazland Team'
    )
    try:
        send_mail(op_subject, op_body, from_email, [op_email], fail_silently=True)
    except Exception as exc:
        logger.error('Failed to send waitlist operator notification to %s: %s', op_email, exc)


def notify_waitlist_for_departure(departure):
    """
    Notify all waitlisted tourists that a spot has opened on this departure.
    Called whenever departure.spots_left increases (cancellation / refund).
    Returns number of emails sent.
    """
    from .models import WaitlistEntry
    from django.db.models import Q

    entries = WaitlistEntry.objects.filter(
        Q(departure=departure) | Q(tour=departure.tour, departure_label=str(departure.start_date))
    ).distinct()

    if not entries.exists():
        return 0

    from_email = settings.DEFAULT_FROM_EMAIL
    site       = _site_url()
    months     = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    dep_label  = (
        f"{departure.start_date.day} {months[departure.start_date.month - 1]}"
        f" {departure.start_date.year}"
    )
    sent = 0

    for entry in entries:
        name    = (entry.name or 'Traveller').strip()
        subject = f'A spot just opened — {departure.tour.title}'
        body    = (
            f'Hi {name},\n\n'
            f'Good news — a spot has opened for:\n\n'
            f'  Tour:       {departure.tour.title}\n'
            f'  Departure:  {dep_label}\n\n'
            f'Spots are filled on a first-come, first-served basis — book now:\n'
            f'{site}/tour_detail_page.html?slug={departure.tour.slug}\n\n'
            f'Kind regards,\nThe Kavkazland Team'
        )
        try:
            send_mail(subject, body, from_email, [entry.email], fail_silently=False)
            sent += 1
        except Exception as exc:
            logger.error('Failed to send waitlist open notification to %s: %s', entry.email, exc)

    return sent


def notify_admin_tour_submitted(tour) -> bool:
    """
    Tell the admin a tour is waiting for approval.

    Only an admin can move review -> live, so without this the tour sits in the
    queue unseen while the operator waits on a decision nobody knows to make.
    """
    admin_email = (getattr(settings, 'ADMIN_NOTIFICATION_EMAIL', None)
                   or getattr(settings, 'DEFAULT_FROM_EMAIL', None))
    if not admin_email:
        logger.warning('No ADMIN_NOTIFICATION_EMAIL — tour submission not announced.')
        return False

    op = tour.operator
    who = op.full_name or op.email
    subject = f'[Admin] Tour awaiting approval — {tour.title}'
    body = (
        f'An operator has submitted a tour for review.\n\n'
        f'Tour:      {tour.title} (/{tour.slug})\n'
        f'Operator:  {who} ({op.email})\n'
        f'Verified:  {"yes" if getattr(op, "is_verified", False) else "NO"}\n'
        f'Duration:  {getattr(tour, "days", "-")} days\n'
        f'Price:     {getattr(tour, "price", "-")} {getattr(tour, "currency", "")}\n\n'
        f'It stays invisible to travellers until you publish it.\n'
        f'Review: /admin/tours/tour/?q={tour.slug}\n'
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [admin_email],
                  fail_silently=False)
        logger.info('Tour-submitted notice sent for %s', tour.slug)
        return True
    except Exception as exc:
        logger.error('Could not send tour-submitted notice for %s: %s', tour.slug, exc)
        return False


def _operator_email(tour):
    op = tour.operator
    return op.email if op and op.email else ''


def notify_operator_tour_approved(tour) -> bool:
    """
    Tell the guide their tour is live.

    Publishing was a bare queryset.update(): the tour went live and the person
    who wrote it was told nothing. They had no way to find out except opening
    the dashboard on the off chance, so a tour could be taking bookings for
    days before its guide realised.
    """
    to = _operator_email(tour)
    if not to:
        return False
    site = getattr(settings, 'FRONTEND_URL', '') or _site_url()
    op = tour.operator
    body = (
        f'Hi {(op.first_name or "").strip() or "there"},\n\n'
        f'Good news — "{tour.title}" has been approved and is now live on '
        f'Kavkazland. Travellers can find it and book it from today.\n\n'
        f'View it: {site}/tour_detail_page.html?slug={tour.slug}\n'
        f'Manage it: {site}/operator-dashboard.html\n\n'
        f'A few things worth checking now it is public:\n'
        f'  - your departure dates are still the ones you want to run\n'
        f'  - your bank details are on file, or we cannot pay you\n\n'
        f'The Kavkazland Team\n'
    )
    try:
        send_mail(f'Your tour is live: {tour.title}', body,
                  settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
        logger.info('Tour-approved notice sent for %s', tour.slug)
        return True
    except Exception as exc:
        logger.error('Could not send tour-approved notice for %s: %s', tour.slug, exc)
        return False


def notify_operator_tour_rejected(tour, reason='') -> bool:
    """
    Tell the guide their tour was sent back, and why.

    Rejection moved the tour to draft silently. Without a reason the guide
    cannot fix whatever the problem was, so they either resubmit the same thing
    or give up — both of which cost you a listing.
    """
    to = _operator_email(tour)
    if not to:
        return False
    site = getattr(settings, 'FRONTEND_URL', '') or _site_url()
    op = tour.operator
    why = (f'What needs changing:\n{reason.strip()}\n\n' if (reason or '').strip()
           else 'No specific reason was recorded. Reply to this email and we will explain.\n\n')
    body = (
        f'Hi {(op.first_name or "").strip() or "there"},\n\n'
        f'We have sent "{tour.title}" back to draft, so it is not visible to '
        f'travellers yet.\n\n'
        f'{why}'
        f'Nothing is lost — everything you wrote is still there. Edit it and '
        f'submit again whenever you are ready:\n'
        f'{site}/operator-tour-create.html?slug={tour.slug}\n\n'
        f'The Kavkazland Team\n'
    )
    try:
        send_mail(f'Changes needed on: {tour.title}', body,
                  settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
        logger.info('Tour-rejected notice sent for %s', tour.slug)
        return True
    except Exception as exc:
        logger.error('Could not send tour-rejected notice for %s: %s', tour.slug, exc)
        return False
