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

    def _cancel_as_guide(self, bk, reason=None):
        client = APIClient()
        client.force_authenticate(self.guide)
        payload = {'reason': reason} if reason else {}
        return client.patch(f'/api/v1/bookings/{bk.pk}/cancel/', payload, format='json')

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

    def test_the_notice_carries_the_reason_the_guide_gave(self):
        """
        The count says a guide is cancelling; only the reason says whether to
        worry. Four dropped for "in hospital" and four for "found a better
        group" are the same number and different problems.
        """
        with self.settings(ADMIN_NOTIFICATION_EMAIL='ops@kavkazland.com'):
            self._cancel_as_guide(self._booking(), reason='Road to Mestia closed by snow')
        notice = self._admin_mail()[0]
        self.assertIn('Road to Mestia closed by snow', notice.body)
        self.assertIn('Road to Mestia closed by snow', notice.alternatives[0][0])

    def test_a_reason_with_html_in_it_cannot_reach_our_inbox_as_markup(self):
        with self.settings(ADMIN_NOTIFICATION_EMAIL='ops@kavkazland.com'):
            self._cancel_as_guide(self._booking(), reason='<script>alert(1)</script> sorry')
        html = self._admin_mail()[0].alternatives[0][0]
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_a_cancellation_with_no_reason_says_so_rather_than_going_quiet(self):
        """
        The form makes it required, but the API does not — so a blank one has to
        read as blank, not as an ordinary notice with a gap where the reason was.
        """
        with self.settings(ADMIN_NOTIFICATION_EMAIL='ops@kavkazland.com'):
            self._cancel_as_guide(self._booking())
        notice = self._admin_mail()[0]
        self.assertIn('none given', notice.body)
        self.assertIn('gave no reason', notice.alternatives[0][0])

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


class ChurnColumnTest(TestCase):
    """
    The churn column exists to catch what the guide-cancellation count cannot:
    a guide whose friends book to manufacture demand and then cancel
    themselves. Those read as ordinary traveller cancellations one at a time.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(email='a@example.com', password='x')
        cls.guide = User.objects.create_user(email='guide@example.com', password='x',
                                             role=User.Role.OPERATOR, first_name='Sandro')
        cls.tour = Tour.objects.create(operator=cls.guide, title='Ushba', country='Georgia',
                                       destination='M', price_adult=Decimal('500'),
                                       currency='USD', status=Tour.Status.LIVE, max_group=8)

    def setUp(self):
        self.client.force_login(self.admin)

    def _bookings(self, total, cancelled, cancelled_by=Booking.CancelledBy.TOURIST):
        for i in range(total):
            Booking.objects.create(
                tour=self.tour, adults=1, first_name='A', last_name=str(i),
                email=f'{i}@example.com', price_adult=Decimal('500'),
                total_price=Decimal('500'), currency='USD',
                status=(Booking.Status.CANCELLED if i < cancelled
                        else Booking.Status.CONFIRMED),
                cancelled_by=(cancelled_by if i < cancelled else ''))

    def test_the_column_is_on_the_guide_list(self):
        r = self.client.get('/admin/users/user/')
        self.assertContains(r, 'Churn')

    def test_traveller_cancellations_still_count_toward_churn(self):
        """The whole point — the guide-initiated count would show zero here."""
        self._bookings(total=10, cancelled=6)
        r = self.client.get('/admin/users/user/')
        self.assertContains(r, '6/10 (60%)')

    def test_a_guide_with_almost_no_bookings_is_left_alone(self):
        """Two out of three is not a signal, and colouring it red would lie."""
        self._bookings(total=3, cancelled=2)
        r = self.client.get('/admin/users/user/')
        self.assertContains(r, '2/3 (67%)')
        self.assertNotContains(r, '#c0392b">2/3')

    def test_a_high_rate_is_flagged(self):
        self._bookings(total=10, cancelled=5)
        r = self.client.get('/admin/users/user/')
        self.assertContains(r, '#c0392b')

    def test_a_healthy_rate_is_not(self):
        self._bookings(total=20, cancelled=2)
        r = self.client.get('/admin/users/user/')
        self.assertContains(r, '2/20 (10%)')
        self.assertNotContains(r, '#c0392b">2/20')

    def test_a_guide_with_no_bookings_shows_nothing(self):
        r = self.client.get('/admin/users/user/')
        self.assertContains(r, '—')
