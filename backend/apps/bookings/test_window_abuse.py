"""
Cycling the free window.

Every use of it costs us the card fee, and a booking made and dropped holds a
seat out of sale in the meantime — so an account doing it repeatedly damages a
guide's departure even though the money comes back. Past a limit the window is
simply not offered; nothing is blocked.

The trap in any rule like this is counting cancellations that were not the
traveller's doing, so most of what follows is about what must not count.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings import cooling
from apps.bookings.models import Booking
from apps.tours.models import DepartureDate, Tour
from apps.users.models import User


class WindowAbuseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guide = User.objects.create_user(email='g@example.com', password='x',
                                             role=User.Role.OPERATOR)
        cls.traveller = User.objects.create_user(email='t@example.com', password='x')
        cls.tour = Tour.objects.create(operator=cls.guide, title='Ushba', country='Georgia',
                                       destination='Mestia', price_adult=Decimal('500'),
                                       currency='USD', status=Tour.Status.LIVE, max_group=8)

    def _cancelled_inside_window(self, by=Booking.CancelledBy.TOURIST, days_ago=1,
                                 tourist=None):
        when = timezone.now() - timedelta(days=days_ago)
        return Booking.objects.create(
            tour=self.tour, tourist=tourist or self.traveller, adults=1,
            first_name='A', last_name='B', email='t@example.com',
            price_adult=Decimal('500'), total_price=Decimal('500'), currency='USD',
            status=Booking.Status.CANCELLED, cancelled_by=by,
            cancelled_at=when, cooling_off_until=when + timedelta(minutes=10),
        )

    _dep_offset = 0

    def _book(self, days_out=60):
        # A departure date is unique per tour, so repeated bookings need
        # distinct ones — several of these tests book the same tour many times.
        type(self)._dep_offset += 1
        start = date.today() + timedelta(days=days_out + type(self)._dep_offset)
        dep = DepartureDate.objects.create(tour=self.tour, start_date=start,
                                           end_date=start + timedelta(days=3),
                                           spots_total=8, spots_left=8)
        client = APIClient()
        client.force_authenticate(self.traveller)
        res = client.post('/api/v1/bookings/', {
            'tour_slug': self.tour.slug, 'departure_id': dep.pk, 'adults': 1,
            'first_name': 'A', 'last_name': 'B', 'email': 't@example.com',
            'phone': '+70000000000', 'country': 'GE',
        }, format='json')
        self.assertIn(res.status_code, (200, 201), res.data)
        return Booking.objects.get(pk=res.data['id'])

    # ── the rule ────────────────────────────────────────────────────────────

    def test_a_first_time_traveller_gets_the_window(self):
        self.assertTrue(cooling.grants_window(self.traveller))
        self.assertIsNotNone(self._book().cooling_off_until)

    def test_a_second_booking_still_gets_one(self):
        """Changing your mind once is not a pattern."""
        self._cancelled_inside_window()
        self.assertTrue(cooling.grants_window(self.traveller))
        self.assertIsNotNone(self._book().cooling_off_until)

    def test_the_third_booking_gets_none(self):
        for _ in range(cooling.COOLING_OFF_ABUSE_LIMIT):
            self._cancelled_inside_window()
        self.assertFalse(cooling.grants_window(self.traveller))
        self.assertIsNone(self._book().cooling_off_until)

    def test_the_booking_still_works_it_just_has_no_free_window(self):
        """Nothing is blocked — the tour's own policy simply applies at once."""
        for _ in range(cooling.COOLING_OFF_ABUSE_LIMIT):
            self._cancelled_inside_window()
        bk = self._book()
        self.assertEqual(bk.status, Booking.Status.PENDING)
        self.assertIsNone(bk.cooling_off_until)

    def test_it_forgets_after_the_window_of_time_passes(self):
        for _ in range(cooling.COOLING_OFF_ABUSE_LIMIT + 2):
            self._cancelled_inside_window(days_ago=cooling.COOLING_OFF_ABUSE_DAYS + 5)
        self.assertTrue(cooling.grants_window(self.traveller))

    # ── what must not count ─────────────────────────────────────────────────

    def test_a_guide_cancelling_is_not_held_against_the_traveller(self):
        for _ in range(4):
            self._cancelled_inside_window(by=Booking.CancelledBy.OPERATOR)
        self.assertTrue(cooling.grants_window(self.traveller))

    def test_a_guide_never_responding_is_not_held_against_them_either(self):
        for _ in range(4):
            self._cancelled_inside_window(by=Booking.CancelledBy.OPERATOR_TIMEOUT)
        self.assertTrue(cooling.grants_window(self.traveller))

    def test_our_own_admin_cancellations_do_not_count(self):
        for _ in range(4):
            self._cancelled_inside_window(by=Booking.CancelledBy.ADMIN)
        self.assertTrue(cooling.grants_window(self.traveller))

    def test_cancelling_after_the_window_closed_does_not_count(self):
        """They paid the policy price for those, so they are not free uses."""
        for _ in range(4):
            when = timezone.now() - timedelta(days=1)
            Booking.objects.create(
                tour=self.tour, tourist=self.traveller, adults=1,
                first_name='A', last_name='B', email='t@example.com',
                price_adult=Decimal('500'), total_price=Decimal('500'), currency='USD',
                status=Booking.Status.CANCELLED, cancelled_by=Booking.CancelledBy.TOURIST,
                cancelled_at=when, cooling_off_until=when - timedelta(hours=2),
            )
        self.assertTrue(cooling.grants_window(self.traveller))

    def test_someone_elses_cancellations_do_not_count(self):
        other = User.objects.create_user(email='other@example.com', password='x')
        for _ in range(4):
            self._cancelled_inside_window(tourist=other)
        self.assertTrue(cooling.grants_window(self.traveller))

    def test_an_anonymous_booking_is_not_charged_for_a_stranger(self):
        self.assertTrue(cooling.grants_window(None))

    def test_a_party_of_four_counts_once_not_four_times(self):
        """The count is per booking, as the terms say — not per traveller."""
        b = self._cancelled_inside_window()
        b.adults, b.children = 3, 1
        b.save(update_fields=['adults', 'children'])
        self.assertEqual(cooling.recent_window_cancellations(self.traveller), 1)

    def test_booking_repeatedly_without_cancelling_costs_nothing(self):
        """
        Bookings are not counted, only uses of the window. Wording that said
        otherwise made this look like a limit on how often you may book.
        """
        for _ in range(6):
            self.assertIsNotNone(self._book().cooling_off_until)


class TheTravellerIsToldTest(WindowAbuseTest):
    """
    Withholding the window is only fair if the person is told, and every page
    otherwise keeps promising one. The API answers per user when signed in.
    """

    def _ask(self, authed=True):
        client = APIClient()
        if authed:
            client.force_authenticate(self.traveller)
        return client.get('/api/v1/bookings/cooling-off/')

    def test_a_signed_in_traveller_is_told_they_still_get_one(self):
        res = self._ask()
        self.assertIs(res.data['you_get_one'], True)

    def test_and_told_when_they_no_longer_do(self):
        for _ in range(cooling.COOLING_OFF_ABUSE_LIMIT):
            self._cancelled_inside_window()
        self.assertIs(self._ask().data['you_get_one'], False)

    def test_a_signed_out_visitor_is_told_nothing_about_anyone(self):
        self.assertNotIn('you_get_one', self._ask(authed=False).data)
