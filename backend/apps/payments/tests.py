"""
The YooKassa webhook is the only payment endpoint with no signature to verify —
YooKassa authenticates by source IP — so it is the one that has to be fenced by
hand.

The attack it must refuse: `yookassa_payment_id` is named for YooKassa but
holds whichever provider took the deposit, Stripe and PayPal included. A
traveller reads their own Stripe session id out of the checkout redirect,
POSTs an unsigned `payment.succeeded` naming it, and their booking is marked
paid without any money moving.

test_forged_event_cannot_settle_a_stripe_booking is the one that matters. The
other two cover the fences in front of it; that one covers the case where both
of those have been misconfigured.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.bookings.models import Booking
from apps.tours.models import DepartureDate, Tour
from apps.users.models import User

WEBHOOK = '/api/v1/payments/webhook/'
YOO_IPS = ['185.71.76.0/27', '127.0.0.0/8']   # last entry so the test client passes


def succeeded(payment_id, amount='1000.00'):
    return {
        'event': 'payment.succeeded',
        'object': {
            'id': payment_id,
            'amount': {'value': amount, 'currency': 'RUB'},
            'metadata': {'payment_type': 'deposit'},
        },
    }


def held(payment_id, instrument=None, amount='1000.00'):
    """A payment created with capture=false, waiting for us to claim it."""
    obj = {
        'id': payment_id,
        'amount': {'value': amount, 'currency': 'RUB'},
        'metadata': {'payment_type': 'deposit'},
    }
    if instrument is not None:
        obj['payment_method'] = {'type': instrument}
    return {'event': 'payment.waiting_for_capture', 'object': obj}


class YooKassaWebhookTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guide = User.objects.create_user(
            email='guide@example.com', password='x', role=User.Role.OPERATOR)
        cls.tourist = User.objects.create_user(
            email='tourist@example.com', password='x', role=User.Role.TOURIST)
        cls.tour = Tour.objects.create(
            operator=cls.guide, title='Elbrus Traverse', country='Russia',
            destination='Mount Elbrus', price_adult=Decimal('500.00'),
            currency='USD', status=Tour.Status.LIVE, max_group=10)
        start = date.today() + timedelta(days=60)
        cls.departure = DepartureDate.objects.create(
            tour=cls.tour, start_date=start, end_date=start + timedelta(days=5),
            spots_total=10, spots_left=10)

    def _booking(self, method, payment_id):
        return Booking.objects.create(
            tour=self.tour, departure=self.departure, tourist=self.tourist,
            departure_date=self.departure.start_date, adults=2,
            first_name='Test', last_name='Booker', email='booker@example.com',
            status=Booking.Status.PENDING, currency='USD',
            price_adult=Decimal('500.00'), total_price=Decimal('1000.00'),
            payment_method=method, yookassa_payment_id=payment_id,
            deposit_status='pending',
        )

    def _post(self, payload):
        return self.client.post(WEBHOOK, payload, content_type='application/json')

    # ── what we are willing to leave held ────────────────────────────────────
    #
    # We ask YooKassa for a hold because the traveller chose card in our UI.
    # That does not stop them picking a wallet on YooKassa's own page, and a
    # wallet holds for two hours against a window of up to twenty-four — so
    # waiting would let the hold die and leave a confirmed booking with a seat
    # and no money. Only a card is left held.

    def _held_booking(self, payment_id):
        b = self._booking('yookassa', payment_id)
        b.capture_status = Booking.Capture.AUTHORISED
        b.save(update_fields=['capture_status'])
        return b

    def _capture_calls(self):
        """Record captures instead of calling YooKassa."""
        from apps.payments import capture as cap
        calls = []
        orig = dict(cap._HANDLERS)
        cap.register('yookassa', lambda bk: calls.append(bk.reference), lambda bk: None)
        self.addCleanup(lambda: (cap._HANDLERS.clear(), cap._HANDLERS.update(orig)))
        return calls

    @override_settings(PAYMENT_METHODS_ENABLED=['yookassa'], YOOKASSA_WEBHOOK_IPS=YOO_IPS)
    def test_a_card_is_left_held(self):
        calls = self._capture_calls()
        self._held_booking('pay-card')
        self._post(held('pay-card', 'bank_card'))
        self.assertEqual(calls, [])

    @override_settings(PAYMENT_METHODS_ENABLED=['yookassa'], YOOKASSA_WEBHOOK_IPS=YOO_IPS)
    def test_a_wallet_is_charged_before_its_two_hours_run_out(self):
        calls = self._capture_calls()
        b = self._held_booking('pay-wallet')
        self._post(held('pay-wallet', 'yoo_money'))
        self.assertEqual(calls, [b.reference])

    @override_settings(PAYMENT_METHODS_ENABLED=['yookassa'], YOOKASSA_WEBHOOK_IPS=YOO_IPS)
    def test_an_instrument_we_do_not_recognise_is_charged_too(self):
        calls = self._capture_calls()
        b = self._held_booking('pay-new')
        self._post(held('pay-new', 'some_method_added_next_year'))
        self.assertEqual(calls, [b.reference])

    @override_settings(PAYMENT_METHODS_ENABLED=['yookassa'], YOOKASSA_WEBHOOK_IPS=YOO_IPS)
    def test_a_payload_that_does_not_say_is_charged_rather_than_trusted(self):
        """
        The dangerous default. Assuming a card when the payload is silent costs
        a dead hold and a seat held against no money; assuming otherwise costs
        only the fee we would have saved.
        """
        calls = self._capture_calls()
        b = self._held_booking('pay-quiet')
        self._post(held('pay-quiet', instrument=None))
        self.assertEqual(calls, [b.reference])

    # ── fence 1: the rail is switched off ────────────────────────────────────

    @override_settings(PAYMENT_METHODS_ENABLED=['stripe', 'paypal'],
                       YOOKASSA_WEBHOOK_IPS=YOO_IPS)
    def test_rejected_while_the_russian_rail_is_disabled(self):
        b = self._booking('yookassa', 'pay-1')
        r = self._post(succeeded('pay-1'))
        self.assertEqual(r.status_code, 403)
        b.refresh_from_db()
        self.assertEqual(b.deposit_status, 'pending')

    # ── fence 2: the allowlist ───────────────────────────────────────────────

    @override_settings(PAYMENT_METHODS_ENABLED=['yookassa'], YOOKASSA_WEBHOOK_IPS=[])
    def test_unset_allowlist_fails_closed(self):
        """
        This used to return True on an empty allowlist and settle the booking.
        Refusing to settle is recoverable; settling for free is not.
        """
        b = self._booking('yookassa', 'pay-2')
        r = self._post(succeeded('pay-2'))
        self.assertEqual(r.status_code, 403)
        b.refresh_from_db()
        self.assertEqual(b.deposit_status, 'pending')

    @override_settings(PAYMENT_METHODS_ENABLED=['yookassa'],
                       YOOKASSA_WEBHOOK_IPS=['185.71.76.0/27'])
    def test_rejected_from_an_ip_outside_yookassas_networks(self):
        b = self._booking('yookassa', 'pay-3')
        r = self._post(succeeded('pay-3'))
        self.assertEqual(r.status_code, 403)
        b.refresh_from_db()
        self.assertEqual(b.deposit_status, 'pending')

    # ── fence 3: the rail the booking was actually charged on ────────────────

    @override_settings(PAYMENT_METHODS_ENABLED=['yookassa', 'stripe'],
                       YOOKASSA_WEBHOOK_IPS=YOO_IPS)
    def test_forged_event_cannot_settle_a_stripe_booking(self):
        """
        The whole point. Even from an allowed IP with the rail enabled, a
        YooKassa event naming a Stripe session id must not settle it — that id
        is visible to the traveller in their own checkout redirect.
        """
        b = self._booking('stripe', 'cs_test_a1b2c3')
        r = self._post(succeeded('cs_test_a1b2c3'))
        self.assertEqual(r.status_code, 200)   # acknowledged, deliberately ignored
        b.refresh_from_db()
        self.assertEqual(b.deposit_status, 'pending',
                         'a YooKassa event must never settle a card booking')
        self.assertEqual(b.deposit_paid, Decimal('0'))

    @override_settings(PAYMENT_METHODS_ENABLED=['yookassa', 'paypal'],
                       YOOKASSA_WEBHOOK_IPS=YOO_IPS)
    def test_forged_event_cannot_cancel_a_paypal_booking(self):
        """The same confusion in the other direction: a forged `canceled` must
        not be able to mark a live card payment failed."""
        b = self._booking('paypal', 'paypal-order-9')
        b.deposit_status = 'paid'
        b.save(update_fields=['deposit_status'])
        self._post({'event': 'payment.canceled',
                    'object': {'id': 'paypal-order-9', 'metadata': {}}})
        b.refresh_from_db()
        self.assertEqual(b.deposit_status, 'paid')

    # ── the legitimate path still works ──────────────────────────────────────

    @override_settings(PAYMENT_METHODS_ENABLED=['yookassa'],
                       YOOKASSA_WEBHOOK_IPS=YOO_IPS)
    def test_a_real_yookassa_event_still_settles_its_own_booking(self):
        b = self._booking('yookassa', 'pay-real')
        r = self._post(succeeded('pay-real'))
        self.assertEqual(r.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.deposit_status, 'paid')
        self.assertGreater(b.deposit_paid, 0)