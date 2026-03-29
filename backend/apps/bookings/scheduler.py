"""
apps/bookings/scheduler.py
Background scheduled jobs using APScheduler + django-apscheduler.

Jobs:
  auto_cancel_expired_bookings  — every hour
  send_deposit_reminders        — every hour
  send_balance_reminders        — every 24 hours
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def auto_cancel_expired_bookings():
    """
    Rule 1 — Ghost bookings: tourist submitted form but never paid deposit.
              Auto-cancel after 24 h. No email (nothing was paid).

    Rule 2 — Unconfirmed deposits: tourist paid but operator didn't confirm in 48 h.
              Auto-cancel + refund notice to tourist.

    Rule 3 — Past-departure stranded: PENDING bookings (deposit paid) where the
              tour has fully ended with a 2-day grace. Catches edge cases that slipped
              past Rule 2 (e.g. last-minute bookings, admin-created records).
              Full refund issued since the tour never ran for this tourist.
    """
    import datetime as _dt
    from .models import Booking
    from .views import send_booking_cancelled_emails

    now   = timezone.now()
    today = now.date()

    # Rule 1: no deposit paid, booking > 24 h old
    ghost_cutoff = now - timedelta(hours=24)
    ghosts = Booking.objects.filter(
        status=Booking.Status.PENDING,
        deposit_status='pending',
        created_at__lte=ghost_cutoff,
    )
    for bk in ghosts:
        bk.status       = Booking.Status.CANCELLED
        bk.cancelled_at = now
        bk.save(update_fields=['status', 'cancelled_at'])
        logger.info('Auto-cancelled ghost booking %s (no deposit within 24 h)', bk.reference)
        try:
            send_booking_cancelled_emails(bk, cancelled_by='system_no_deposit')
        except Exception as exc:
            logger.error('Email error for ghost cancel %s: %s', bk.reference, exc)

    # Rule 2: deposit paid but operator never confirmed, > 48 h old
    confirm_cutoff = now - timedelta(hours=48)
    unconfirmed = Booking.objects.filter(
        status=Booking.Status.PENDING,
        deposit_status='paid',
        confirmed_at__isnull=True,
        created_at__lte=confirm_cutoff,
    )
    for bk in unconfirmed:
        bk.status       = Booking.Status.CANCELLED
        bk.cancelled_at = now
        bk.save(update_fields=['status', 'cancelled_at'])
        logger.info('Auto-cancelled unconfirmed booking %s (operator timeout 48 h)', bk.reference)
        try:
            send_booking_cancelled_emails(bk, cancelled_by='operator_timeout')
        except Exception as exc:
            logger.error('Email error for operator-timeout cancel %s: %s', bk.reference, exc)

    # Rule 3: deposit paid, still PENDING, but tour departure has fully passed (+ 2 day grace)
    stranded = Booking.objects.filter(
        status=Booking.Status.PENDING,
        deposit_status='paid',
        departure_date__isnull=False,
    ).select_related('tour')
    for bk in stranded:
        tour_days = getattr(bk.tour, 'days', 1) or 1
        # Tour end date + 2-day grace before we auto-cancel
        cutoff_date = bk.departure_date + _dt.timedelta(days=tour_days + 1)
        if today < cutoff_date:
            continue
        bk.status           = Booking.Status.CANCELLED
        bk.cancelled_at     = now
        bk.refund_amount    = float(bk.deposit_paid)   # full deposit back — tour never confirmed
        bk.refund_status    = 'pending'                 # flag for manual processing
        bk.save(update_fields=['status', 'cancelled_at', 'refund_amount', 'refund_status'])
        logger.info(
            'Auto-cancelled past-departure stranded booking %s (departure %s, tour %d days)',
            bk.reference, bk.departure_date, tour_days,
        )
        try:
            send_booking_cancelled_emails(bk, cancelled_by='system_past_departure')
        except Exception as exc:
            logger.error('Email error for past-departure cancel %s: %s', bk.reference, exc)


def auto_complete_bookings():
    """
    Mark confirmed bookings as completed 24 h after the tour departure ends.
    End date = departure_date + tour.days - 1 (or departure.end_date if available).
    Also sends a review request email to the tourist.
    """
    from .models import Booking
    from django.core.mail import send_mail
    from django.conf import settings
    import datetime
    import zoneinfo

    now     = timezone.now()
    from_em = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@waybound.com')
    site    = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')

    # Find confirmed bookings whose tour has ended (departure_date + days - 1 < today)
    confirmed = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        departure_date__isnull=False,
    ).select_related('tour', 'departure')

    for bk in confirmed:
        # Use tour's departure timezone for "today"
        tz_name = getattr(bk.tour, 'timezone', '') or 'Europe/Moscow'
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except (KeyError, Exception):
            tz = zoneinfo.ZoneInfo('Europe/Moscow')
        today = now.astimezone(tz).date()

        # Calculate tour end date
        if bk.departure and bk.departure.end_date:
            end_date = bk.departure.end_date
        else:
            tour_days = getattr(bk.tour, 'days', 1) or 1
            end_date = bk.departure_date + datetime.timedelta(days=tour_days - 1)

        # Complete if 24h+ past end date (in tour timezone)
        if today > end_date:
            bk.status = Booking.Status.COMPLETED
            bk.save(update_fields=['status'])
            logger.info('Auto-completed booking %s (tour ended %s)', bk.reference, end_date)

            # Send review request email (skip if tourist already reviewed while still confirmed)
            from apps.reviews.models import TourReview
            already_reviewed = bk.tourist and TourReview.objects.filter(
                tourist=bk.tourist, tour=bk.tour
            ).exists()
            if not already_reviewed:
                name = (bk.first_name or '').strip() or 'Traveller'
                tour_title = bk.tour.title
                review_url = f'{site}/my-bookings.html?review={bk.reference}'
                try:
                    send_mail(
                        f'How was {tour_title}? Leave a review',
                        f'Hi {name},\n\n'
                        f'We hope you enjoyed "{tour_title}"!\n\n'
                        f'Your feedback helps future travellers and supports your guide. '
                        f'It only takes a minute.\n\n'
                        f'Leave a review: {review_url}\n\n'
                        f'Ref: {bk.reference}\n\n'
                        f'Thanks,\nWaybound',
                        from_em, [bk.email], fail_silently=True,
                    )
                    logger.info('Sent review request email for %s', bk.reference)
                except Exception as exc:
                    logger.error('Review request email error for %s: %s', bk.reference, exc)


def send_review_reminders():
    """
    Follow-up reminder 5 days after completion if the tourist hasn't left a review yet.
    """
    from .models import Booking
    from apps.reviews.models import TourReview
    from django.core.mail import send_mail
    from django.conf import settings

    now     = timezone.now()
    from_em = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@waybound.com')
    site    = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')

    # Bookings completed ~5 days ago (window: 5-6 days to avoid duplicates with daily runs)
    lower = now - timedelta(days=6)
    upper = now - timedelta(days=5)

    completed = Booking.objects.filter(
        status=Booking.Status.COMPLETED,
        updated_at__gte=lower,
        updated_at__lt=upper,
    ).select_related('tour')

    for bk in completed:
        if not bk.tourist:
            continue
        # Skip if already reviewed
        if TourReview.objects.filter(tourist=bk.tourist, tour=bk.tour).exists():
            continue

        name = (bk.first_name or '').strip() or 'Traveller'
        review_url = f'{site}/my-bookings.html?review={bk.reference}'
        try:
            send_mail(
                f'Still thinking about {bk.tour.title}? Share your experience',
                f'Hi {name},\n\n'
                f'You completed "{bk.tour.title}" a few days ago and we\'d love to hear how it went.\n\n'
                f'Your review helps other travellers discover great experiences '
                f'and means a lot to your guide.\n\n'
                f'Leave a review: {review_url}\n\n'
                f'Thanks,\nWaybound',
                from_em, [bk.email], fail_silently=True,
            )
            logger.info('Sent review reminder for %s', bk.reference)
        except Exception as exc:
            logger.error('Review reminder email error for %s: %s', bk.reference, exc)


def send_deposit_reminders():
    """
    Nudge tourists who haven't paid their deposit yet:
      - 12 h after booking: first reminder
      - 22 h after booking: final warning (auto-cancel at 24 h)
    """
    from .models import Booking
    from django.core.mail import send_mail
    from django.conf import settings

    now     = timezone.now()
    from_em = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@waybound.com')
    site    = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')

    for hours, label in [(12, 'Reminder'), (22, 'Final reminder — act now')]:
        lower = now - timedelta(hours=hours + 1)
        upper = now - timedelta(hours=hours)
        bookings = Booking.objects.filter(
            status=Booking.Status.PENDING,
            deposit_status='pending',
            created_at__gte=lower,
            created_at__lt=upper,
        ).select_related('tour')
        for bk in bookings:
            name = (bk.first_name or '').strip() or 'Traveller'
            subject = f'{label}: complete your booking for {bk.tour.title}'
            message = (
                f'Hi {name},\n\n'
                f'Your booking for "{bk.tour.title}" is waiting for your deposit payment.\n'
                f'Ref: {bk.reference}\n\n'
                f'Your spot will be released in {24 - hours} hour(s) if payment is not received.\n\n'
                f'Pay now: {site}/my-bookings.html\n\nWaybound'
            )
            try:
                send_mail(subject, message, from_em, [bk.email], fail_silently=True)
                logger.info('Sent deposit %s for %s', label.lower(), bk.reference)
            except Exception as exc:
                logger.error('Deposit reminder email error for %s: %s', bk.reference, exc)


def send_balance_reminders():
    """
    Remind tourists to pay the remaining balance:
      - 7 days before balance_due_date
      - 3 days before balance_due_date
    """
    import datetime
    from .models import Booking
    from django.core.mail import send_mail
    from django.conf import settings

    today   = timezone.now().date()
    from_em = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@waybound.com')
    site    = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')

    for days, label in [(14, '14 days'), (7, '7 days'), (3, '3 days')]:
        target = today + datetime.timedelta(days=days)
        bookings = Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            balance_status='pending',
            balance_due_date=target,
        ).select_related('tour')
        for bk in bookings:
            balance = float(bk.total_price) - float(bk.deposit_paid)
            if balance <= 0:
                continue  # fully paid via deposit — nothing to remind
            name    = (bk.first_name or '').strip() or 'Traveller'
            due_str = bk.balance_due_date.strftime('%d %b %Y')
            subject = f'Balance due in {label}: {bk.tour.title}'
            message = (
                f'Hi {name},\n\n'
                f'Your balance of {bk.currency} {balance:,.2f} for "{bk.tour.title}" '
                f'is due in {label} ({due_str}).\n'
                f'Ref: {bk.reference}\n\n'
                f'Pay now: {site}/my-bookings.html\n\nWaybound'
            )
            try:
                send_mail(subject, message, from_em, [bk.email], fail_silently=True)
                logger.info('Sent balance reminder (%s days) for %s', days, bk.reference)
            except Exception as exc:
                logger.error('Balance reminder email error for %s: %s', bk.reference, exc)


def send_operator_balance_reminders():
    """
    Notify operators about bookings with unpaid balance, with adaptive frequency
    based on how close the next cancellation penalty tier escalation is.

    Frequency table (based on days until NEXT higher penalty tier):
        14+ days  → once per week
        7–13 days → every 3 days
        <7 days / overdue / departure imminent → daily
    """
    import datetime as _dt
    import zoneinfo
    from .models import Booking
    from .views import PLATFORM_DEFAULT_CANCEL_POLICY
    from django.core.mail import send_mail
    from django.conf import settings

    now     = timezone.now()
    today_utc = now.date()
    from_em = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@waybound.com')
    site    = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')

    # Query with a 1-day buffer to account for timezone differences
    bookings = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        balance_status='pending',
        departure_date__gte=today_utc - _dt.timedelta(days=1),
    ).select_related('tour', 'tour__operator')

    for bk in bookings:
        # Use tour timezone for accurate days-to-departure
        tz_name = getattr(bk.tour, 'timezone', '') or 'Europe/Moscow'
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except (KeyError, Exception):
            tz = zoneinfo.ZoneInfo('Europe/Moscow')
        today = now.astimezone(tz).date()
        days_to_dep = (bk.departure_date - today).days
        if days_to_dep < 0:
            continue  # already departed

        # Determine the cancel policy tiers for this booking
        snapshot = bk.cancel_policy_snapshot or PLATFORM_DEFAULT_CANCEL_POLICY

        # Find the NEXT higher penalty tier boundary
        # Sort tiers by days_before_min descending — we walk from the most lenient
        # (furthest out) toward the strictest (closest to departure).
        sorted_tiers = sorted(snapshot, key=lambda t: -(t.get('days_before_min', 0)))

        # Current tier and next (stricter) tier
        current_penalty = 0
        next_tier_days  = None   # days_before_max of the next stricter tier boundary
        next_penalty    = None
        for tier in sorted_tiers:
            mn = tier.get('days_before_min', 0)
            mx = tier.get('days_before_max')
            if days_to_dep >= mn and (mx is None or days_to_dep <= mx):
                current_penalty = tier.get('penalty_pct', 0)
                break

        # Find the next tier the booking will enter (higher penalty, fewer days)
        for tier in sorted_tiers:
            mx = tier.get('days_before_max')
            mn = tier.get('days_before_min', 0)
            pct = tier.get('penalty_pct', 0)
            if pct > current_penalty and days_to_dep > mn:
                # This tier starts at days_before_max (when days_remaining drops to mx)
                next_tier_days = mx if mx is not None else mn
                next_penalty = pct
                break

        # Calculate days until the next tier escalation
        if next_tier_days is not None:
            days_until_escalation = days_to_dep - next_tier_days
        else:
            days_until_escalation = days_to_dep  # no higher tier — use departure as reference

        # Determine required reminder interval (in hours)
        balance_overdue = bk.balance_due_date and bk.balance_due_date < today
        departure_imminent = days_to_dep <= 2

        if balance_overdue or departure_imminent or days_until_escalation < 7:
            interval_hours = 24
        elif days_until_escalation <= 13:
            interval_hours = 72
        else:
            interval_hours = 168  # weekly

        # Check if enough time has passed since last reminder
        if bk.last_balance_reminder_sent:
            hours_since = (now - bk.last_balance_reminder_sent).total_seconds() / 3600
            if hours_since < interval_hours:
                continue

        # Build the email
        op = bk.tour.operator
        if not op or not op.email:
            continue

        op_name  = (op.first_name or '').strip() or 'Operator'
        trav     = f'{bk.first_name} {bk.last_name}'.strip() or 'Traveller'
        balance  = float(bk.total_price) - float(bk.deposit_paid) - float(bk.balance_paid)
        if balance <= 0:
            continue  # fully paid — nothing to remind operator about
        dep_str  = bk.departure_date.strftime('%d %b %Y')
        sym      = {'RUB': '₽', 'USD': '$', 'EUR': '€', 'GBP': '£'}.get(bk.currency, bk.currency + ' ')

        escalation_warning = ''
        if next_penalty is not None and days_until_escalation <= 14:
            escalation_warning = (
                f'\n⚠ Heads up: the cancellation penalty increases from '
                f'{current_penalty}% to {next_penalty}% in {max(1, days_until_escalation)} day(s).\n'
            )

        overdue_note = ''
        if balance_overdue:
            overdue_note = '\n⚠ The balance due date has already passed.\n'

        subject = f'Balance unpaid: {trav} — {bk.tour.title} ({dep_str})'
        message = (
            f'Hi {op_name},\n\n'
            f'Tourist {trav} still has an unpaid balance for their booking.\n\n'
            f'Tour: {bk.tour.title}\n'
            f'Departure: {dep_str}\n'
            f'Booking ref: {bk.reference}\n'
            f'Balance owed: {sym}{balance:,.2f}\n'
            f'Current cancellation penalty: {current_penalty}%\n'
            f'{escalation_warning}{overdue_note}\n'
            f'You can cancel the booking or message the tourist from your dashboard:\n'
            f'{site}/operator-dashboard.html#bookings\n\n'
            f'Waybound'
        )

        try:
            send_mail(subject, message, from_em, [op.email], fail_silently=True)
            bk.last_balance_reminder_sent = now
            bk.save(update_fields=['last_balance_reminder_sent'])
            logger.info(
                'Sent operator balance reminder for %s (escalation in %d days, interval=%dh)',
                bk.reference, days_until_escalation, interval_hours,
            )
        except Exception as exc:
            logger.error('Operator balance reminder error for %s: %s', bk.reference, exc)


def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from django_apscheduler.jobstores import DjangoJobStore

    scheduler = BackgroundScheduler(timezone='UTC')
    scheduler.add_jobstore(DjangoJobStore(), 'default')

    scheduler.add_job(
        auto_cancel_expired_bookings,
        trigger=IntervalTrigger(hours=1),
        id='auto_cancel_expired_bookings',
        name='Auto-cancel expired bookings',
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        send_deposit_reminders,
        trigger=IntervalTrigger(hours=1),
        id='send_deposit_reminders',
        name='Send deposit payment reminders',
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        send_balance_reminders,
        trigger=IntervalTrigger(hours=24),
        id='send_balance_reminders',
        name='Send balance payment reminders (daily)',
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        send_operator_balance_reminders,
        trigger=IntervalTrigger(hours=6),
        id='send_operator_balance_reminders',
        name='Notify operators about unpaid balances (adaptive frequency)',
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        auto_complete_bookings,
        trigger=IntervalTrigger(hours=6),
        id='auto_complete_bookings',
        name='Auto-complete bookings after tour ends',
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        send_review_reminders,
        trigger=IntervalTrigger(hours=24),
        id='send_review_reminders',
        name='Send review reminder emails (5 days after completion)',
        replace_existing=True,
        misfire_grace_time=300,
    )

    try:
        scheduler.start()
        logger.info('APScheduler started with %d jobs.', len(scheduler.get_jobs()))
    except Exception as exc:
        logger.error('APScheduler failed to start: %s', exc)
