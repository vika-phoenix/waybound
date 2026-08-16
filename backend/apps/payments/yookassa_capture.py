"""
apps/payments/yookassa_capture.py
Claiming and dropping a YooKassa card hold.

A payment created with capture=False sits in waiting_for_capture: the money is
held on the card and moves only when we claim it. YooKassa holds a card for 7
days, comfortably past our longest free window.

Only cards. The wallet-backed methods — YooMoney, QIWI, WebMoney and certain
instant mobile banking — hold for 2 hours, which is under our longest window,
so those are charged at booking whichever scheme is running. SBP is a bank
transfer and has nothing to hold. register_rails() wires only 'yookassa' for
that reason.
"""
import logging

from apps.payments.capture import CaptureError

logger = logging.getLogger(__name__)


def _payment(booking):
    """The YooKassa payment behind this booking, and the SDK to act on it."""
    from .views import _yoo_configure

    payment_id = booking.yookassa_payment_id
    if not payment_id:
        raise CaptureError('No YooKassa payment on this booking', retryable=False)
    try:
        yookassa = _yoo_configure()
    except Exception as exc:
        raise CaptureError(f'YooKassa was unreachable: {exc}')
    try:
        return yookassa, payment_id, yookassa.Payment.find_one(payment_id)
    except Exception as exc:
        raise CaptureError(f'Could not read the payment: {exc}')


def capture_yookassa(booking):
    """Take the money the card is holding."""
    import uuid

    yookassa, payment_id, payment = _payment(booking)
    state = getattr(payment, 'status', '')

    # Arriving twice is normal here: the sweep retries and webhooks duplicate.
    if state == 'succeeded':
        logger.info('YooKassa payment %s was already captured', payment_id)
        return
    if state == 'canceled':
        raise CaptureError('The hold on your card was released before payment '
                           'could be taken.', retryable=False)
    if state != 'waiting_for_capture':
        raise CaptureError(f'The payment is not ready to charge (status: {state})')

    try:
        result = yookassa.Payment.capture(payment_id, {}, str(uuid.uuid4()))
    except Exception as exc:
        raise CaptureError(f'YooKassa refused the charge: {exc}')

    if getattr(result, 'status', '') != 'succeeded':
        raise CaptureError('The charge did not complete '
                           f'(status: {getattr(result, "status", "unknown")})')
    logger.info('Captured YooKassa payment %s for %s', payment_id, booking.reference)


def void_yookassa(booking):
    """Release the hold without charging it. Costs nothing."""
    import uuid

    yookassa, payment_id, payment = _payment(booking)
    state = getattr(payment, 'status', '')
    if state == 'canceled':
        logger.info('YooKassa payment %s was already released', payment_id)
        return
    if state != 'waiting_for_capture':
        # Cancelling a payment that already succeeded is not a void, it is a
        # refund, and that is a different decision made somewhere else.
        raise CaptureError(f'Nothing to release (status: {state})', retryable=False)

    yookassa.Payment.cancel(payment_id, str(uuid.uuid4()))
    logger.info('Released YooKassa hold %s for %s', payment_id, booking.reference)
