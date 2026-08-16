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
        bk.cancelled_by = Booking.CancelledBy.SYSTEM_NO_DEPOSIT
        bk.save(update_fields=['status', 'cancelled_at', 'cancelled_by'])
        bk.release_seats()
        logger.info('Auto-cancelled ghost booking %s (no deposit within 24 h)', bk.reference)
        try:
            send_booking_cancelled_emails(bk, cancelled_by='system_no_deposit')
        except Exception as exc:
            logger.error('Email error for ghost cancel %s: %s', bk.reference, exc)

    # Rule 2: deposit paid but the booking never got confirmed, > 48 h old.
    #
    # Under instant book this should never fire: paying confirms the booking on
    # both rails. It stays as a backstop for the one case that can still leave a
    # paid booking pending — a payment recorded by hand with the amount entered
    # before the money actually arrived. Cancelling a paid booking and refunding
    # it in full is the right outcome there too.
    from .views import _compute_refund, _issue_yookassa_refund

    confirm_cutoff = now - timedelta(hours=48)
    unconfirmed = Booking.objects.filter(
        status=Booking.Status.PENDING,
        deposit_status='paid',
        confirmed_at__isnull=True,
        created_at__lte=confirm_cutoff,
    )
    for bk in unconfirmed:
        # Compute full refund (operator fault → 100%)
        refund_amount, penalty_pct, tier_label = _compute_refund(bk, cancelled_by='system')
        bk.status        = Booking.Status.CANCELLED
        bk.cancelled_at  = now
        bk.cancelled_by  = Booking.CancelledBy.OPERATOR_TIMEOUT
        bk.refund_amount = refund_amount

        # Attempt automatic YooKassa refund
        if refund_amount > 0:
            success, msg = _issue_yookassa_refund(bk, refund_amount)
            bk.refund_status = 'issued' if success else ('manual' if msg == 'bank' else 'pending')
        else:
            bk.refund_status = 'none'

        bk.save(update_fields=['status', 'cancelled_at', 'cancelled_by',
                               'refund_amount', 'refund_status'])
        bk.release_seats()
        logger.info('Auto-cancelled unconfirmed booking %s (operator timeout 48 h, refund=%.2f %s)',
                     bk.reference, refund_amount, bk.refund_status)
        try:
            send_booking_cancelled_emails(bk, cancelled_by='operator_timeout')
            from .views import notify_admin_guide_cancellation
            notify_admin_guide_cancellation(bk, timed_out=True)
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
        refund_amount, _, _ = _compute_refund(bk, cancelled_by='system')
        bk.status        = Booking.Status.CANCELLED
        bk.cancelled_at  = now
        bk.cancelled_by  = Booking.CancelledBy.SYSTEM_PAST
        bk.refund_amount = refund_amount

        if refund_amount > 0:
            success, msg = _issue_yookassa_refund(bk, refund_amount)
            bk.refund_status = 'issued' if success else ('manual' if msg == 'bank' else 'pending')
        else:
            bk.refund_status = 'none'

        bk.save(update_fields=['status', 'cancelled_at', 'cancelled_by',
                               'refund_amount', 'refund_status'])
        bk.release_seats()
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
    from_em = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@kavkazland.com')
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
            # The trip has run, so the guide is now owed their share. This is
            # what settings.html promises them: paid within 5 working days of
            # completion. Nothing here moves money — it puts the booking on the
            # admin's "who am I paying this week" list.
            fields = ['status']
            if bk.payout_status == 'not_due' and bk.payout_amount > 0:
                bk.payout_status = 'due'
                fields.append('payout_status')
            bk.save(update_fields=fields)
            logger.info('Auto-completed booking %s (tour ended %s), payout %s',
                        bk.reference, end_date, bk.payout_status)

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
                        f'Thanks,\nKavkazland',
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
    from_em = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@kavkazland.com')
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
                f'Thanks,\nKavkazland',
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
    from django.conf import settings

    from apps.mail import lang_for, send

    now  = timezone.now()
    site = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')
    LABELS = {'en': {12: 'Reminder', 22: 'Final reminder — act now'},
              'ru': {12: 'Напоминание', 22: 'Последнее напоминание — нужно действовать'}}

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
            lang = lang_for(bk.tourist)
            page = 'my-bookings_ru.html' if lang == 'ru' else 'my-bookings.html'
            send(bk.email, 'deposit_reminder', lang,
                 url=f'{site}/{page}',
                 name=(bk.first_name or '').strip() or ('Путешественник' if lang == 'ru'
                                                        else 'Traveller'),
                 tour=bk.tour.title,
                 ref=bk.reference,
                 label=LABELS[lang][hours],
                 hours_left=24 - hours)


def send_balance_reminders():
    """
    Remind tourists to pay the remaining balance:
      - 7 days before balance_due_date
      - 3 days before balance_due_date
    """
    import datetime
    from .models import Booking
    from django.conf import settings

    from apps.mail import lang_for, send

    today = timezone.now().date()
    site  = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')
    LABELS = {'en': {14: '14 days', 7: '7 days', 3: '3 days'},
              'ru': {14: '14 дней', 7: '7 дней', 3: '3 дня'}}

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
            lang = lang_for(bk.tourist)
            page = 'my-bookings_ru.html' if lang == 'ru' else 'my-bookings.html'
            send(bk.email, 'balance_reminder', lang,
                 url=f'{site}/{page}',
                 name=(bk.first_name or '').strip()
                      or ('Путешественник' if lang == 'ru' else 'Traveller'),
                 tour=bk.tour.title,
                 ref=bk.reference,
                 label=LABELS[lang][days],
                 amount=f'{bk.currency} {balance:,.2f}',
                 due_date=bk.balance_due_date.strftime('%d.%m.%Y' if lang == 'ru'
                                                       else '%d %b %Y'))


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
    from_em = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@kavkazland.com')
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
            f'Kavkazland'
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


def purge_verification_documents():
    """
    Drop verification scans once the decision they supported is old enough.

    Runs the management command so there is one implementation and it can also
    be invoked by hand — a retention rule that only exists inside a scheduler
    is one nobody can demonstrate when asked to.
    """
    from django.core.management import call_command
    try:
        call_command('purge_verification_documents')
    except Exception as exc:
        logger.error('Verification document purge failed: %s', exc, exc_info=True)


def capture_due_authorisations():
    """
    Charge the cards whose free window has shut.

    Runs often, because the shortest window is 30 minutes and an authorisation
    left uncaptured eventually expires on its own — at which point the money is
    gone and the seat is still held.

    A failure here is not an error to swallow: it leaves a confirmed booking
    with nothing behind it, so it starts a grace period and tells the traveller.
    """
    from apps.payments.capture import capture_booking
    from .models import Booking

    now = timezone.now()
    due = Booking.objects.filter(
        capture_status=Booking.Capture.AUTHORISED,
        status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
        cooling_off_until__isnull=False,
        cooling_off_until__lte=now,
    )

    ok = failed = 0
    for bk in due:
        if capture_booking(bk):
            ok += 1
            continue
        failed += 1
        try:
            send_capture_failed_email(bk)
        except Exception as exc:
            logger.error('Capture-failure email error for %s: %s', bk.reference, exc)

    if ok or failed:
        logger.info('Capture sweep: %d charged, %d failed.', ok, failed)


def cancel_unfixed_captures():
    """
    Give up on bookings whose card was never fixed.

    The seat has been held since booking on the promise of money that never
    arrived, so it goes back on sale. One reminder goes out at the halfway
    point first — a failed capture is far more often an expired card than
    anyone being difficult.
    """
    from .models import Booking
    from .views import send_booking_cancelled_emails

    now = timezone.now()
    stuck = Booking.objects.filter(
        capture_status=Booking.Capture.FAILED,
        capture_grace_until__isnull=False,
    ).exclude(status=Booking.Status.CANCELLED)

    reminded = cancelled = 0
    for bk in stuck:
        if now < bk.capture_grace_until:
            # Halfway reminder, once. capture_attempts moves on every retry, so
            # it cannot be the flag — a dedicated one keeps the two apart.
            half = bk.capture_grace_until - bk.capture_grace_period(now) / 2
            if now >= half and not bk.capture_reminder_sent:
                try:
                    send_capture_failed_email(bk, reminder=True)
                    bk.capture_reminder_sent = True
                    bk.save(update_fields=['capture_reminder_sent'])
                    reminded += 1
                except Exception as exc:
                    logger.error('Capture reminder error for %s: %s', bk.reference, exc)
            continue

        bk.status       = Booking.Status.CANCELLED
        bk.cancelled_at = now
        bk.cancelled_by = Booking.CancelledBy.SYSTEM_NO_DEPOSIT
        bk.cancel_reason = ('Card could not be charged when the free cancellation '
                            'window closed, and was not fixed in time.')
        bk.save(update_fields=['status', 'cancelled_at', 'cancelled_by', 'cancel_reason'])
        bk.release_seats()
        cancelled += 1
        logger.info('Cancelled %s — capture never succeeded.', bk.reference)
        try:
            send_booking_cancelled_emails(bk, cancelled_by='system_no_deposit')
        except Exception as exc:
            logger.error('Email error for capture cancel %s: %s', bk.reference, exc)

    if reminded or cancelled:
        logger.info('Capture grace sweep: %d reminded, %d cancelled.', reminded, cancelled)


def send_capture_failed_email(booking, reminder=False):
    """
    Tell the traveller their card did not go through, and by when to fix it.

    In their own language: this one is time-limited, costs them a seat if they
    miss it, and is the worst of all our messages to send to someone who has
    been reading the site in Russian.
    """
    from django.conf import settings

    from apps.mail import lang_for, send

    lang = lang_for(booking.tourist)
    site = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')
    page = 'my-bookings_ru.html' if lang == 'ru' else 'my-bookings.html'
    deadline = booking.capture_grace_until
    fallback = ('Банк отклонил списание.' if lang == 'ru'
                else 'Your bank declined the charge.')

    send(booking.email,
         'capture_reminder' if reminder else 'capture_failed',
         lang,
         url=f'{site}/{page}',
         name=(booking.first_name or '').strip() or ('Путешественник' if lang == 'ru'
                                                     else 'Traveller'),
         tour=booking.tour.title,
         ref=booking.reference,
         reason=booking.capture_last_error or fallback,
         deadline=deadline.strftime('%H:%M UTC, %d %b') if deadline else '—')


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

    # Fixed frequency, whichever scheme is running. Slowing these down while
    # nothing defers saved about a tenth of a second of CPU a day and bought a
    # branch that only matters in the one situation nobody rehearses: a switch
    # back to charging at booking, with authorisations still outstanding and an
    # hour of extra lag on claiming money that is sitting on someone's card.
    #
    # Fifteen minutes is set by the shortest free window being thirty, so a
    # capture is never more than half a window late.
    scheduler.add_job(
        capture_due_authorisations,
        trigger=IntervalTrigger(minutes=15),
        id='capture_due_authorisations',
        name='Charge cards whose cancellation window has closed',
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        cancel_unfixed_captures,
        trigger=IntervalTrigger(minutes=30),
        id='cancel_unfixed_captures',
        name='Chase, then release, seats whose card never cleared',
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.add_job(
        purge_verification_documents,
        # Weekly, not daily. The frequency is not the retention period, it is
        # the lag past it: weekly means a scan lives at most 97 days against a
        # published promise of 90. Monthly would stretch that to 120 and make
        # the privacy policy inaccurate.
        trigger=IntervalTrigger(hours=168),
        id='purge_verification_documents',
        name='Delete verification scans past the retention period',
        replace_existing=True,
        misfire_grace_time=3600,
    )

    try:
        scheduler.start()
        logger.info('APScheduler started with %d jobs.', len(scheduler.get_jobs()))
    except Exception as exc:
        logger.error('APScheduler failed to start: %s', exc)
