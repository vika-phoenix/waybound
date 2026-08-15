"""
Seats on a departure.

They used to come off in exactly one place — the guide pressing confirm — while
the Stripe and PayPal webhooks set a booking straight to CONFIRMED without
going through it. So a paid international booking took no seat, and cancelling
it handed uncounted seats back and put other people's seats on sale again.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.tours.models import DepartureDate, Tour
from apps.users.models import User


class SeatAccountingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guide = User.objects.create_user(email='guide@example.com', password='x',
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

    def _booking(self, adults=2, **over):
        data = dict(tour=self.tour, departure=self.dep, departure_date=self.dep.start_date,
                    tourist=self.traveller, adults=adults,
                    first_name='A', last_name='B', email='t@example.com',
                    price_adult=Decimal('500'), total_price=Decimal('1000'),
                    currency='USD', status=Booking.Status.PENDING)
        data.update(over)
        return Booking.objects.create(**data)

    def _left(self):
        self.dep.refresh_from_db()
        return self.dep.spots_left

    # ── Taking ──────────────────────────────────────────────────────────────

    def test_confirming_takes_the_seats(self):
        bk = self._booking()
        client = APIClient()
        client.force_authenticate(self.guide)
        client.patch(f'/api/v1/bookings/{bk.pk}/confirm/', {}, format='json')
        self.assertEqual(self._left(), 6)

    def test_taking_twice_takes_them_once(self):
        bk = self._booking()
        bk.take_seats()
        bk.take_seats()
        self.assertEqual(self._left(), 6)

    def test_a_card_payment_takes_the_seats(self):
        """
        The bug: this path confirms the booking without going through the
        guide's confirm action, so it never deducted anything.
        """
        from apps.payments.views import _settle
        bk = self._booking(deposit_status='pending')
        _settle(bk, "deposit", 300.0)
        self.assertEqual(self._left(), 6)
        bk.refresh_from_db()
        self.assertEqual(bk.status, Booking.Status.CONFIRMED)
        self.assertTrue(bk.seats_held)

    # ── Releasing ───────────────────────────────────────────────────────────

    def test_cancelling_gives_the_seats_back(self):
        bk = self._booking()
        bk.take_seats()
        client = APIClient()
        client.force_authenticate(self.traveller)
        client.patch(f'/api/v1/bookings/{bk.pk}/cancel/', {}, format='json')
        self.assertEqual(self._left(), 8)

    def test_cancelling_a_booking_that_never_took_a_seat_gives_nothing_back(self):
        """
        This is what put a departure above its own capacity: an unheld booking
        cancelling still credited seats, and other travellers' seats went back
        on sale.
        """
        held = self._booking(adults=3)
        held.take_seats()
        self.assertEqual(self._left(), 5)

        never_paid = self._booking(adults=2)
        client = APIClient()
        client.force_authenticate(self.traveller)
        client.patch(f'/api/v1/bookings/{never_paid.pk}/cancel/', {}, format='json')
        self.assertEqual(self._left(), 5,
                         "the other booking's seats must stay taken")

    def test_releasing_twice_releases_once(self):
        bk = self._booking()
        bk.take_seats()
        bk.release_seats()
        bk.release_seats()
        self.assertEqual(self._left(), 8)

    def test_the_unpaid_sweep_gives_seats_back(self):
        from apps.bookings.scheduler import auto_cancel_expired_bookings
        from django.utils import timezone
        bk = self._booking()
        bk.take_seats()
        Booking.objects.filter(pk=bk.pk).update(
            created_at=timezone.now() - timedelta(hours=30))
        auto_cancel_expired_bookings()
        self.assertEqual(self._left(), 8)

    # ── The whole round trip ────────────────────────────────────────────────

    def test_a_departure_never_exceeds_its_own_capacity(self):
        a = self._booking(adults=3); a.take_seats()
        b = self._booking(adults=2); b.take_seats()
        c = self._booking(adults=2)          # never paid, never held
        self.assertEqual(self._left(), 3)
        for bk in (a, b, c):
            bk.release_seats()
        self.assertEqual(self._left(), 8)


class ProcessingFeeTierTest(TestCase):
    """
    1% in the top tier is the card fee, not a penalty — it has to cover the
    real cost at both ends of the price range or it is the wrong number.
    """

    @classmethod
    def setUpTestData(cls):
        cls.guide = User.objects.create_user(email='g2@example.com', password='x',
                                             role=User.Role.OPERATOR)
        cls.traveller = User.objects.create_user(email='t2@example.com', password='x')

    def _cancel_far_out(self, price):
        from apps.bookings.views import PLATFORM_DEFAULT_CANCEL_POLICY, _compute_refund
        tour = Tour.objects.create(operator=self.guide, title=f'T{price}', country='Georgia',
                                   destination='M', price_adult=Decimal(price),
                                   currency='USD', status=Tour.Status.LIVE, max_group=8)
        bk = Booking.objects.create(
            tour=tour, departure_date=date.today() + timedelta(days=90),
            tourist=self.traveller, adults=1,
            first_name='A', last_name='B', email='t2@example.com',
            price_adult=Decimal(price), total_price=Decimal(price), currency='USD',
            deposit_paid=Decimal(price) * Decimal('0.30'), deposit_status='paid',
            status=Booking.Status.CONFIRMED,
            cancel_policy_snapshot=PLATFORM_DEFAULT_CANCEL_POLICY)
        return _compute_refund(bk, cancelled_by='tourist')

    def test_the_top_tier_keeps_one_percent(self):
        refund, penalty_pct, label = self._cancel_far_out('500')
        self.assertEqual(penalty_pct, 1)
        # Deposit 150, penalty 1% of 500 = 5, refund 145.
        self.assertAlmostEqual(refund, 145.0, places=2)

    def test_it_covers_the_card_fee_on_an_expensive_tour(self):
        """2.9% + $0.30 of a 30% deposit on 2000 is $17.70."""
        refund, _, _ = self._cancel_far_out('2000')
        kept = 600.0 - refund
        self.assertAlmostEqual(kept, 20.0, places=2)
        self.assertGreater(kept, 17.70)

    def test_the_label_does_not_promise_a_full_refund(self):
        _, _, label = self._cancel_far_out('500')
        self.assertIn('1%', label)
        self.assertNotIn('Full refund', label)

    def test_a_guide_cancellation_still_refunds_everything(self):
        """A traveller must not pay a fee because their guide pulled out."""
        from apps.bookings.views import PLATFORM_DEFAULT_CANCEL_POLICY, _compute_refund
        tour = Tour.objects.create(operator=self.guide, title='X', country='Georgia',
                                   destination='M', price_adult=Decimal('500'),
                                   currency='USD', status=Tour.Status.LIVE, max_group=8)
        bk = Booking.objects.create(
            tour=tour, departure_date=date.today() + timedelta(days=90),
            tourist=self.traveller, adults=1,
            first_name='A', last_name='B', email='t2@example.com',
            price_adult=Decimal('500'), total_price=Decimal('500'), currency='USD',
            deposit_paid=Decimal('150'), deposit_status='paid',
            status=Booking.Status.CONFIRMED,
            cancel_policy_snapshot=PLATFORM_DEFAULT_CANCEL_POLICY)
        refund, _, _ = _compute_refund(bk, cancelled_by='operator')
        self.assertAlmostEqual(refund, 150.0, places=2)

    def test_the_cooling_off_window_still_refunds_everything(self):
        from django.utils import timezone
        from apps.bookings.views import PLATFORM_DEFAULT_CANCEL_POLICY, _compute_refund
        tour = Tour.objects.create(operator=self.guide, title='Y', country='Georgia',
                                   destination='M', price_adult=Decimal('500'),
                                   currency='USD', status=Tour.Status.LIVE, max_group=8)
        bk = Booking.objects.create(
            tour=tour, departure_date=date.today() + timedelta(days=90),
            tourist=self.traveller, adults=1,
            first_name='A', last_name='B', email='t2@example.com',
            price_adult=Decimal('500'), total_price=Decimal('500'), currency='USD',
            deposit_paid=Decimal('150'), deposit_status='paid',
            status=Booking.Status.CONFIRMED,
            cooling_off_until=timezone.now() + timedelta(minutes=20),
            cancel_policy_snapshot=PLATFORM_DEFAULT_CANCEL_POLICY)
        refund, _, _ = _compute_refund(bk, cancelled_by='tourist')
        self.assertAlmostEqual(refund, 150.0, places=2)
