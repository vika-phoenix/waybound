"""
Guards on the two operator actions that can strand a traveller.

**Pause** only delists a tour — every trip already sold still has to run. A
guide who reads "paused" as "cancelled" simply stops showing up. So pausing a
tour with live bookings answers 409 with the numbers, and only goes through on
a second, explicit request. It is a warning, not a block: pausing a tour you
are still running is a legitimate thing to want.

**Departure cancel** is the action that actually calls a trip off. Its preview
must not touch anything — a guide has to be able to ask "what would this cost?"
without it costing anything.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.tours.models import DepartureDate, Tour
from apps.users.models import User


class _TourTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email='guide@example.com', password='x', role=User.Role.OPERATOR)
        cls.tourist = User.objects.create_user(
            email='tourist@example.com', password='x', role=User.Role.TOURIST)

        cls.tour = Tour.objects.create(
            operator=cls.owner, title='Elbrus Traverse', country='Russia',
            destination='Mount Elbrus', price_adult=Decimal('500.00'),
            currency='USD', status=Tour.Status.LIVE, max_group=10,
        )
        cls.start = date.today() + timedelta(days=60)
        cls.departure = DepartureDate.objects.create(
            tour=cls.tour, start_date=cls.start,
            end_date=cls.start + timedelta(days=5),
            spots_total=10, spots_left=10,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _book(self, adults=2, children=0, paid='1000.00'):
        return Booking.objects.create(
            tour=self.tour, departure=self.departure, tourist=self.tourist,
            departure_date=self.start, adults=adults, children=children,
            first_name='Test', last_name='Booker', email='booker@example.com',
            status=Booking.Status.CONFIRMED, currency='USD',
            price_adult=Decimal('500.00'), price_child=Decimal('250.00'),
            total_price=Decimal(paid), deposit_paid=Decimal(paid),
            payment_method='bank',
        )

    @property
    def _tour_url(self):
        return f'/api/v1/tours/{self.tour.slug}/'

    @property
    def _cancel_url(self):
        return f'/api/v1/tours/{self.tour.slug}/departures/{self.departure.id}/cancel/'


class PauseWarningTest(_TourTestBase):
    def test_pause_without_bookings_needs_no_confirmation(self):
        r = self.client.patch(self._tour_url, {'status': 'paused'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.tour.refresh_from_db()
        self.assertEqual(self.tour.status, Tour.Status.PAUSED)

    def test_pause_with_bookings_warns_and_does_not_pause(self):
        self._book(adults=2, children=1)
        self._book(adults=3)
        r = self.client.patch(self._tour_url, {'status': 'paused'}, format='json')

        self.assertEqual(r.status_code, 409)
        self.assertTrue(r.data['requires_confirmation'])
        self.assertEqual(r.data['active_bookings'], 2)
        self.assertEqual(r.data['travellers'], 6)
        self.assertEqual(r.data['next_departure'], str(self.start))

        self.tour.refresh_from_db()
        self.assertEqual(self.tour.status, Tour.Status.LIVE,
                         'the warning must not pause the tour on its own')

    def test_pause_goes_through_once_confirmed(self):
        self._book()
        r = self.client.patch(self._tour_url,
                              {'status': 'paused', 'confirm': True}, format='json')
        self.assertEqual(r.status_code, 200)
        self.tour.refresh_from_db()
        self.assertEqual(self.tour.status, Tour.Status.PAUSED)

    def test_cancelled_bookings_do_not_trigger_the_warning(self):
        b = self._book()
        b.status = Booking.Status.CANCELLED
        b.save(update_fields=['status'])
        r = self.client.patch(self._tour_url, {'status': 'paused'}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_unpause_is_never_gated(self):
        """Putting a tour back on sale harms nobody, so it must never be blocked."""
        self.tour.status = Tour.Status.PAUSED
        self.tour.save(update_fields=['status'])
        self._book()
        r = self.client.patch(self._tour_url, {'status': 'live'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.tour.refresh_from_db()
        self.assertEqual(self.tour.status, Tour.Status.LIVE)


class DepartureCancelTest(_TourTestBase):
    def test_preview_reports_the_damage_and_changes_nothing(self):
        self._book(adults=2, paid='1000.00')
        self._book(adults=1, children=1, paid='800.00')

        r = self.client.post(self._cancel_url, {}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['preview'])
        self.assertEqual(r.data['bookings_affected'], 2)
        self.assertEqual(r.data['travellers'], 4)
        self.assertEqual(r.data['refund_total'], 1800.00)

        self.departure.refresh_from_db()
        self.assertNotEqual(self.departure.status, DepartureDate.Status.CANCELLED)
        self.assertEqual(
            Booking.objects.filter(status=Booking.Status.CONFIRMED).count(), 2,
            'a preview must not cancel anything')

    def test_confirm_cancels_the_departure_and_every_booking_on_it(self):
        b1 = self._book(adults=2)
        b2 = self._book(adults=1)

        r = self.client.post(self._cancel_url,
                             {'confirm': True, 'reason': 'Too few sign-ups'},
                             format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['cancelled_bookings'], 2)

        self.departure.refresh_from_db()
        self.assertEqual(self.departure.status, DepartureDate.Status.CANCELLED)
        for b in (b1, b2):
            b.refresh_from_db()
            self.assertEqual(b.status, Booking.Status.CANCELLED)
            self.assertEqual(b.refund_amount, b.deposit_paid,
                             'an operator cancellation refunds in full')

    def test_a_failed_refund_still_cancels_the_booking(self):
        """
        'bank' has no automatic rail, so the refund cannot succeed here. The
        traveller must still be told their trip is off — believing it is still
        running is worse than waiting on a refund.
        """
        b = self._book()
        self.client.post(self._cancel_url, {'confirm': True}, format='json')
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.CANCELLED)
        self.assertEqual(b.refund_status, 'manual')

    def test_another_guide_cannot_cancel_this_departure(self):
        stranger = User.objects.create_user(
            email='stranger@example.com', password='x', role=User.Role.OPERATOR)
        self.client.force_authenticate(stranger)
        r = self.client.post(self._cancel_url, {'confirm': True}, format='json')
        self.assertEqual(r.status_code, 403)
        self.departure.refresh_from_db()
        self.assertNotEqual(self.departure.status, DepartureDate.Status.CANCELLED)

    def test_cancelling_twice_is_rejected(self):
        self.client.post(self._cancel_url, {'confirm': True}, format='json')
        r = self.client.post(self._cancel_url, {'confirm': True}, format='json')
        self.assertEqual(r.status_code, 400)


class OperatorTourListDeparturesTest(_TourTestBase):
    """The dashboard cancels a departure by id, so the list has to carry them."""

    def test_only_future_departures_are_listed(self):
        past = date.today() - timedelta(days=10)
        DepartureDate.objects.create(
            tour=self.tour, start_date=past, end_date=past + timedelta(days=3),
            spots_total=8, spots_left=8)

        r = self.client.get('/api/v1/tours/operator/')
        self.assertEqual(r.status_code, 200)
        deps = r.data['results'][0]['departures']
        self.assertEqual([d['start_date'] for d in deps], [str(self.start)])
        self.assertEqual(deps[0]['id'], self.departure.id)