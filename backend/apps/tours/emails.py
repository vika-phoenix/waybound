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

        from apps.mail import lang_for, send as send_mail_catalogued
        lang = lang_for(booking.tourist)
        page = 'my-bookings_ru.html' if lang == 'ru' else 'my-bookings.html'
        if send_mail_catalogued(
                recipient, 'tour_changed', lang,
                url=f'{site}/{page}',
                booking=booking,
                name=(booking.first_name or '').strip()
                     or ('Путешественник' if lang == 'ru' else 'Traveller'),
                tour=tour.title,
                changes=change_summary,
                deadline=(f'{window_hours} ч.' if lang == 'ru'
                          else f'{window_hours} hours from now')):
            sent += 1

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

    from apps.mail import lang_for, send

    t_lang = lang_for(getattr(entry, 'tourist', None))
    page = 'tour_detail_page_ru.html' if t_lang == 'ru' else 'tour_detail_page.html'
    send(entry.email, 'waitlist_joined', t_lang,
         url=f'{site}/{page}?slug={tour.slug}',
         name=name, tour=tour.title, departure=dep_str)

    op = tour.operator
    send(op.email, 'operator_waitlist_entry', lang_for(op),
         url=f'{site}/operator-tour-create.html?slug={tour.slug}',
         name=name, tour=tour.title, departure=dep_str)


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

    from apps.mail import lang_for, send

    for entry in entries:
        lang = lang_for(getattr(entry, 'tourist', None))
        page = 'tour_detail_page_ru.html' if lang == 'ru' else 'tour_detail_page.html'
        if send(entry.email, 'waitlist_spot_open', lang,
                url=f'{site}/{page}?slug={departure.tour.slug}',
                name=(entry.name or 'Traveller').strip(),
                tour=departure.tour.title, departure=dep_label):
            sent += 1

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
    from apps.mail import lang_for, send
    lang = lang_for(op)
    page = 'tour_detail_page_ru.html' if lang == 'ru' else 'tour_detail_page.html'
    return send(to, 'tour_live', lang,
                url=f'{site}/{page}?slug={tour.slug}',
                name=(op.first_name or '').strip() or ('Гид' if lang == 'ru' else 'there'),
                tour=tour.title)


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
    from apps.mail import lang_for, send
    lang = lang_for(op)
    why = (reason or '').strip() or (
        'Конкретная причина не записана — ответьте на это письмо, и мы объясним.'
        if lang == 'ru' else
        'No specific reason was recorded. Reply to this email and we will explain.')
    return send(to, 'tour_changes_needed', lang,
                url=f'{site}/operator-tour-create.html?slug={tour.slug}',
                name=(op.first_name or '').strip() or ('Гид' if lang == 'ru' else 'there'),
                tour=tour.title, reason=why)
