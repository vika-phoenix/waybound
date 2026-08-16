"""
apps/payments/capture.py
The seam between "charge this booking now" and whichever rail holds its money.

Deferred capture means authorising the card at booking and only charging it
once the free cancellation window shuts. A cancellation before that costs
nobody anything: there is no payment to reverse, only an authorisation to drop.

Three rails, three different clocks on how long an authorisation survives:

  Stripe    7 days
  PayPal    ~29 days, honoured for 3
  YooKassa  7 days on cards, but 2 hours on YooMoney wallets, QIWI, WebMoney
            and certain instant mobile banking

Our longest window is 24 hours, which fits everywhere except that last group.
Those are charged outright — CAPTURE_CAPABLE_METHODS is what decides, and a
method missing from it simply keeps today's behaviour.

The per-rail calls are deliberately the last thing wired up. Everything that
happens *after* a capture fails is the risky half, so it is built and tested
first, against a seam that can be faked.
"""
import logging

logger = logging.getLogger(__name__)


class CaptureError(Exception):
    """
    A capture that failed for a reason the traveller may be able to fix.

    The message reaches them, in an email and on their bookings page, so it
    must read as a decline reason and never as an exception.
    """

    def __init__(self, message, retryable=True):
        super().__init__(message)
        self.retryable = retryable


# What a traveller is told when the real reason is ours, not their bank's.
# Raw exception text is logged, never stored: capture_last_error is shown to
# whoever made the booking, so internals must not reach it.
GENERIC_FAILURE = 'The payment could not be completed. Please try again.'


# Rails whose authorisations outlive our longest cooling-off window. Anything
# not listed here is charged at booking time exactly as it is today.
CAPTURE_CAPABLE_METHODS = set()


def supports_deferred_capture(method):
    return method in CAPTURE_CAPABLE_METHODS


def should_defer_capture(booking):
    """
    Whether this particular payment should authorise now and charge later.

    False for a retry after a failed capture, and that is the important case.
    The traveller has already had their free window — its closing is *why* we
    were capturing — so a retry takes the money outright. Granting a fresh
    window on every retry would turn a wallet of dead cards into an unlimited
    free hold on a seat, which is a worse hole than the one deferred capture
    was built to close.
    """
    from django.utils import timezone
    from apps.bookings import cooling
    from apps.bookings.models import Booking

    # The scheme decides. Under a flat 30-minute window the card is charged at
    # booking like any shop, so no authorisation is ever left outstanding and
    # the capture sweeps have nothing to find.
    if not cooling.defers_capture():
        return False
    if booking.capture_status in (Booking.Capture.FAILED, Booking.Capture.CAPTURED):
        return False
    if not supports_deferred_capture(booking.payment_method):
        return False
    cooling = getattr(booking, 'cooling_off_until', None)
    if not cooling or cooling <= timezone.now():
        # No window left to wait out — nothing to defer for.
        return False
    return True


# The registry the rails fill in. Each entry is (capture_fn, void_fn), both
# taking a Booking and returning None on success or raising CaptureError.
_HANDLERS = {}


def register(method, capture_fn, void_fn):
    """Wire a rail in. Called from each provider module at import time."""
    _HANDLERS[method] = (capture_fn, void_fn)
    CAPTURE_CAPABLE_METHODS.add(method)


def capture_booking(booking):
    """
    Claim the money a booking's authorisation is holding.

    Returns True on success. On failure the booking is left in FAILED with its
    grace deadline set, and False is returned — callers are schedulers and
    views that need to carry on rather than blow up.
    """
    from apps.bookings.models import Booking

    if booking.capture_status != Booking.Capture.AUTHORISED:
        logger.info('Capture skipped for %s: status is %s',
                    booking.reference, booking.capture_status)
        return False

    handler = _HANDLERS.get(booking.payment_method)
    if not handler:
        # An authorisation we have no way to claim. Failing loudly is right:
        # the money is real and sitting on someone's card.
        logger.error('No capture handler for %s on booking %s',
                     booking.payment_method, booking.reference)
        booking.mark_capture_failed(GENERIC_FAILURE)
        return False

    try:
        handler[0](booking)
    except CaptureError as exc:
        logger.warning('Capture failed for %s: %s', booking.reference, exc)
        booking.mark_capture_failed(str(exc))
        return False
    except Exception as exc:                       # noqa: BLE001 — see below
        # An unexpected error is not proof the charge did not go through, so
        # this must not cancel anything on its own. It lands in FAILED like any
        # other, and the grace period gives a human time to look.
        logger.exception('Capture blew up for %s', booking.reference)
        booking.mark_capture_failed(GENERIC_FAILURE)
        return False

    booking.capture_attempts = (booking.capture_attempts or 0) + 1
    booking.save(update_fields=['capture_attempts'])
    booking.mark_capture_settled()
    logger.info('Captured %s', booking.reference)
    return True


def void_booking(booking):
    """
    Drop an authorisation without charging it — what a cancellation inside the
    free window should do. Costs nothing, on any rail.
    """
    from apps.bookings.models import Booking

    if booking.capture_status != Booking.Capture.AUTHORISED:
        return False

    handler = _HANDLERS.get(booking.payment_method)
    if not handler:
        logger.error('No void handler for %s on booking %s',
                     booking.payment_method, booking.reference)
        return False

    try:
        handler[1](booking)
    except Exception as exc:                       # noqa: BLE001
        # A void that fails leaves the authorisation to expire on its own,
        # which costs us nothing either. Worth knowing about, not worth
        # blocking a cancellation the traveller already asked for.
        logger.exception('Void failed for %s: %s', booking.reference, exc)
        return False

    booking.capture_status = Booking.Capture.VOIDED
    booking.save(update_fields=['capture_status'])
    logger.info('Voided authorisation for %s', booking.reference)
    return True
