"""
What happens when a capture fails.

Deferred capture moves the charge from booking time to the moment the free
cancellation window shuts, so cancelling inside that window costs nobody
anything. The price is a new failure mode: a card that worked at booking can
decline a day later, and that leaves a confirmed booking holding a seat with
no money behind it.

This is the half that is built and tested first, against a faked rail, because
it is the half that can quietly lose a seat or hold one forever.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from apps.bookings import scheduler
from apps.bookings.models import Booking
from apps.payments import capture as cap
from apps.tours.models import DepartureDate, Tour
from apps.users.models import User


class CaptureBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guide = User.objects.create_user(email='g@example.com', password='x',
                                             role=User.Role.OPERATOR)
        cls.traveller = User.objects.create_user(email='t@example.com', password='x')
        cls.tour = Tour.objects.create(operator=cls.guide, title='Ushba', country='Georgia',
                                       destination='Mestia', price_adult=Decimal('500'),
                                       currency='USD', status=Tour.Status.LIVE, max_group=8)

    def setUp(self):
        start = date.today() + timedelta(days=45)
        self.dep = DepartureDate.objects.create(
            tour=self.tour, start_date=start, end_date=start + timedelta(days=4),
            spots_total=8, spots_left=8)
        self._orig_handlers = dict(cap._HANDLERS)
        self._orig_methods = set(cap.CAPTURE_CAPABLE_METHODS)

    def tearDown(self):
        cap._HANDLERS.clear()
        cap._HANDLERS.update(self._orig_handlers)
        cap.CAPTURE_CAPABLE_METHODS.clear()
        cap.CAPTURE_CAPABLE_METHODS.update(self._orig_methods)

    def _booking(self, adults=2, **over):
        data = dict(tour=self.tour, departure=self.dep, departure_date=self.dep.start_date,
                    tourist=self.traveller, adults=adults,
                    first_name='A', last_name='B', email='t@example.com',
                    price_adult=Decimal('500'), total_price=Decimal('1000'),
                    currency='USD', status=Booking.Status.CONFIRMED,
                    payment_method='stripe',
                    capture_status=Booking.Capture.AUTHORISED)
        data.update(over)
        return Booking.objects.create(**data)

    def _rail(self, capture_raises=None):
        """Register a fake rail so the seam can be exercised without a provider."""
        calls = {'capture': 0, 'void': 0}

        def _capture(bk):
            calls['capture'] += 1
            if capture_raises:
                raise capture_raises

        def _void(bk):
            calls['void'] += 1

        cap.register('stripe', _capture, _void)
        return calls

    def _left(self):
        self.dep.refresh_from_db()
        return self.dep.spots_left


class GraceWindowTest(CaptureBase):

    def test_a_distant_departure_gets_a_day_to_fix_the_card(self):
        bk = self._booking()
        self.assertEqual(bk.capture_grace_period(), timedelta(hours=24))

    def test_an_imminent_departure_gets_three_hours(self):
        soon = date.today() + timedelta(days=5)
        bk = self._booking(departure_date=soon)
        self.assertEqual(bk.capture_grace_period(), timedelta(hours=3))

    def test_a_booking_with_no_date_is_treated_as_distant(self):
        bk = self._booking(departure_date=None)
        self.assertEqual(bk.capture_grace_period(), timedelta(hours=24))

    def test_the_deadline_is_set_once_and_never_pushed_back(self):
        """
        Otherwise someone with a wallet of dead cards retries forever and holds
        the seat indefinitely — the same free hold capture was meant to close.
        """
        bk = self._booking()
        first = bk.mark_capture_failed('card_declined')
        bk.mark_capture_failed('card_declined again')
        bk.refresh_from_db()
        self.assertEqual(bk.capture_grace_until, first)
        self.assertEqual(bk.capture_attempts, 2)


class CaptureSeamTest(CaptureBase):

    def test_a_clean_capture_marks_the_booking_charged(self):
        self._rail()
        bk = self._booking()
        self.assertTrue(cap.capture_booking(bk))
        bk.refresh_from_db()
        self.assertEqual(bk.capture_status, Booking.Capture.CAPTURED)
        self.assertEqual(bk.capture_last_error, '')

    def test_a_declined_card_starts_the_grace_period(self):
        self._rail(capture_raises=cap.CaptureError('Insufficient funds'))
        bk = self._booking()
        self.assertFalse(cap.capture_booking(bk))
        bk.refresh_from_db()
        self.assertEqual(bk.capture_status, Booking.Capture.FAILED)
        self.assertIn('Insufficient funds', bk.capture_last_error)
        self.assertIsNotNone(bk.capture_grace_until)

    def test_an_unexpected_error_does_not_escape(self):
        """
        A crash is not proof the charge failed, so it must not cancel anything
        on its own — it lands in FAILED like any other and a human gets time.
        """
        self._rail(capture_raises=RuntimeError('connection reset'))
        bk = self._booking()
        self.assertFalse(cap.capture_booking(bk))
        bk.refresh_from_db()
        self.assertEqual(bk.capture_status, Booking.Capture.FAILED)
        self.assertEqual(bk.status, Booking.Status.CONFIRMED)

    def test_a_rail_we_cannot_claim_fails_loudly(self):
        bk = self._booking(payment_method='some_new_wallet')
        self.assertFalse(cap.capture_booking(bk))
        bk.refresh_from_db()
        self.assertEqual(bk.capture_status, Booking.Capture.FAILED)

    def test_capturing_something_already_charged_does_nothing(self):
        calls = self._rail()
        bk = self._booking(capture_status=Booking.Capture.CAPTURED)
        self.assertFalse(cap.capture_booking(bk))
        self.assertEqual(calls['capture'], 0)

    def test_voiding_releases_without_charging(self):
        calls = self._rail()
        bk = self._booking()
        self.assertTrue(cap.void_booking(bk))
        bk.refresh_from_db()
        self.assertEqual(bk.capture_status, Booking.Capture.VOIDED)
        self.assertEqual(calls['capture'], 0)
        self.assertEqual(calls['void'], 1)


class CaptureSweepTest(CaptureBase):

    def test_only_bookings_past_their_window_are_charged(self):
        calls = self._rail()
        now = timezone.now()
        self._booking(cooling_off_until=now - timedelta(minutes=1))
        self._booking(cooling_off_until=now + timedelta(hours=5))
        scheduler.capture_due_authorisations()
        self.assertEqual(calls['capture'], 1)

    def test_a_failed_sweep_emails_the_traveller(self):
        self._rail(capture_raises=cap.CaptureError('Card expired'))
        self._booking(cooling_off_until=timezone.now() - timedelta(minutes=1))
        mail.outbox = []
        scheduler.capture_due_authorisations()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('could not charge', mail.outbox[0].subject.lower())


class GraceSweepTest(CaptureBase):

    def _failed(self, grace_hours, departure_days=45):
        bk = self._booking(departure_date=date.today() + timedelta(days=departure_days))
        bk.take_seats()
        bk.capture_status = Booking.Capture.FAILED
        bk.capture_grace_until = timezone.now() + timedelta(hours=grace_hours)
        bk.save(update_fields=['capture_status', 'capture_grace_until'])
        return bk

    def test_a_booking_inside_its_grace_is_left_alone(self):
        bk = self._failed(grace_hours=20)
        scheduler.cancel_unfixed_captures()
        bk.refresh_from_db()
        self.assertEqual(bk.status, Booking.Status.CONFIRMED)
        self.assertEqual(self._left(), 6)

    def test_past_the_deadline_the_seat_goes_back_on_sale(self):
        bk = self._failed(grace_hours=-1)
        self.assertEqual(self._left(), 6)
        scheduler.cancel_unfixed_captures()
        bk.refresh_from_db()
        self.assertEqual(bk.status, Booking.Status.CANCELLED)
        self.assertEqual(self._left(), 8)

    def test_the_halfway_nudge_goes_out_once(self):
        bk = self._failed(grace_hours=6)          # 24 h grace, so halfway is behind us
        mail.outbox = []
        scheduler.cancel_unfixed_captures()
        scheduler.cancel_unfixed_captures()
        bk.refresh_from_db()
        self.assertTrue(bk.capture_reminder_sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('reminder', mail.outbox[0].subject.lower())

    def test_an_already_cancelled_booking_is_not_cancelled_again(self):
        bk = self._failed(grace_hours=-1)
        bk.status = Booking.Status.CANCELLED
        bk.save(update_fields=['status'])
        scheduler.cancel_unfixed_captures()
        bk.refresh_from_db()
        self.assertIsNone(bk.cancelled_at)
