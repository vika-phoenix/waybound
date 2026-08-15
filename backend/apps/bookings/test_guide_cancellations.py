"""
Guide cancellations are the ones that cost us money.

A traveller cancelling is business. A guide pulling out of a paid booking
refunds the traveller in full, leaves the guide's payout at zero either way,
and leaves the platform holding the processor's fee. Every cancellation used to
look identical in the database, so that pattern was invisible.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core import mail
from django.test import TestCase
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.tours.models import DepartureDate, Tour
from apps.users.models import User


class CancelledByTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guide = User.objects.create_user(email='guide@example.com', password='x',
                                             role=User.Role.OPERATOR, first_name='Sandro')
        cls.traveller = User.objects.create_user(email='t@example.com', password='x')
        cls.tour = Tour.objects.create(operator=cls.guide, title='Ushba Base Camp',
                                       country='Georgia', destination='Mestia',
                                       price_adult=Decimal('800'), currency='USD',
                                       status=Tour.Status.LIVE, max_group=8)

    _n = 0

    def _booking(self, **over):
        # A departure is unique per (tour, start_date), so each booking in a
        # test needs its own date.
        CancelledByTest._n += 1
        start = date.today() + timedelta(days=60 + CancelledByTest._n)
        dep = DepartureDate.objects.create(tour=self.tour, start_date=start,
                                           end_date=start + timedelta(days=4),
                                           spots_total=8, spots_left=6)
        data = dict(tour=self.tour, departure=dep, departure_date=start,
                    tourist=self.traveller, adults=2,
                    first_name='Ann', last_name='B', email='t@example.com',
                    price_adult=Decimal('800'), total_price=Decimal('1600'),
                    currency='USD', deposit_paid=Decimal('480'),
                    deposit_status='paid', status=Booking.Status.CONFIRMED)
        data.update(over)
        return Booking.objects.create(**data)

    def _cancel_as(self, user, booking):
        client = APIClient()
        client.force_authenticate(user)
        return client.patch(f'/api/v1/bookings/{booking.pk}/cancel/', {}, format='json')

    def test_a_traveller_cancelling_is_recorded_as_such(self):
        bk = self._booking()
        self._cancel_as(self.traveller, bk)
        bk.refresh_from_db()
        self.assertEqual(bk.cancelled_by, Booking.CancelledBy.TOURIST)

    def test_a_guide_cancelling_is_recorded_as_such(self):
        bk = self._booking()
        self._cancel_as(self.guide, bk)
        bk.refresh_from_db()
        self.assertEqual(bk.cancelled_by, Booking.CancelledBy.OPERATOR)

    def test_the_two_are_distinguishable(self):
        """The whole point: they used to be one indistinguishable event."""
        self._cancel_as(self.traveller, self._booking())
        self._cancel_as(self.guide, self._booking())
        self.assertEqual(
            Booking.objects.filter(cancelled_by=Booking.CancelledBy.OPERATOR).count(), 1)
        self.assertEqual(
            Booking.objects.filter(cancelled_by=Booking.CancelledBy.TOURIST).count(), 1)


class GuideCancellationNoticeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guide = User.objects.create_user(email='guide@example.com', password='x',
                                             role=User.Role.OPERATOR, first_name='Sandro',
                                             last_name='Beridze')
        cls.traveller = User.objects.create_user(email='t@example.com', password='x')
        cls.tour = Tour.objects.create(operator=cls.guide, title='Ushba Base Camp',
                                       country='Georgia', destination='Mestia',
                                       price_adult=Decimal('800'), currency='USD',
                                       status=Tour.Status.LIVE, max_group=8)

    def setUp(self):
        mail.outbox = []

    def _booking(self, paid=True):
        start = date.today() + timedelta(days=60)
        return Booking.objects.create(
            tour=self.tour, departure_date=start, tourist=self.traveller, adults=2,
            first_name='Ann', last_name='B', email='t@example.com',
            price_adult=Decimal('800'), total_price=Decimal('1600'), currency='USD',
            deposit_paid=Decimal('480') if paid else Decimal('0'),
            deposit_status='paid' if paid else 'pending',
            status=Booking.Status.CONFIRMED)

    def _cancel_as_guide(self, bk):
        client = APIClient()
        client.force_authenticate(self.guide)
        return client.patch(f'/api/v1/bookings/{bk.pk}/cancel/', {}, format='json')

    def _admin_mail(self):
        return [m for m in mail.outbox if 'Guide cancellation' in m.subject]

    def test_we_are_told_when_a_guide_cancels_a_paid_booking(self):
        with self.settings(ADMIN_NOTIFICATION_EMAIL='ops@kavkazland.com'):
            self._cancel_as_guide(self._booking())
        notices = self._admin_mail()
        self.assertEqual(len(notices), 1, [m.subject for m in mail.outbox])
        self.assertIn('ops@kavkazland.com', notices[0].to)

    def test_the_notice_counts_how_many_times_this_guide_has_done_it(self):
        """One is a bad week. The number is what turns it into a pattern."""
        with self.settings(ADMIN_NOTIFICATION_EMAIL='ops@kavkazland.com'):
            self._cancel_as_guide(self._booking())
            self._cancel_as_guide(self._booking())
            self._cancel_as_guide(self._booking())
        subjects = [m.subject for m in self._admin_mail()]
        self.assertTrue(any('(1 for' in s for s in subjects), subjects)
        self.assertTrue(any('(3 for' in s for s in subjects), subjects)

    def test_the_guide_is_named_in_the_subject(self):
        with self.settings(ADMIN_NOTIFICATION_EMAIL='ops@kavkazland.com'):
            self._cancel_as_guide(self._booking())
        self.assertIn('Sandro Beridze', self._admin_mail()[0].subject)

    def test_no_notice_when_nothing_had_been_paid(self):
        """Nothing was refunded, so nothing was lost and there is nothing to flag."""
        with self.settings(ADMIN_NOTIFICATION_EMAIL='ops@kavkazland.com'):
            self._cancel_as_guide(self._booking(paid=False))
        self.assertEqual(self._admin_mail(), [])

    def test_a_traveller_cancelling_raises_no_notice(self):
        bk = self._booking()
        client = APIClient()
        client.force_authenticate(self.traveller)
        with self.settings(ADMIN_NOTIFICATION_EMAIL='ops@kavkazland.com'):
            client.patch(f'/api/v1/bookings/{bk.pk}/cancel/', {}, format='json')
        self.assertEqual(self._admin_mail(), [])

    def test_a_missing_admin_address_does_not_break_the_cancellation(self):
        with self.settings(ADMIN_NOTIFICATION_EMAIL=None, DEFAULT_FROM_EMAIL=None):
            res = self._cancel_as_guide(self._booking())
        self.assertEqual(res.status_code, 200, getattr(res, 'data', None))

    def test_the_user_admin_shows_the_count(self):
        admin_user = User.objects.create_superuser(email='a@example.com', password='x')
        self._cancel_as_guide(self._booking())
        self.client.force_login(admin_user)
        r = self.client.get("/admin/users/user/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Cancelled')
