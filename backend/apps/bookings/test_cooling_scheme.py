"""
Switching the free-cancellation scheme.

The window used to be stated in eight places and computed in a ninth, so
widening it left five published pages promising terms the code no longer
kept — two of them contractual. The bands and the words are one object now,
and this holds that together.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.bookings import cooling
from apps.bookings.models import Booking
from apps.tours.models import DepartureDate, Tour
from apps.users.models import User


class WindowMathTest(TestCase):

    @override_settings(COOLING_OFF_SCHEME='tiered')
    def test_the_tiered_scheme_scales_with_the_departure(self):
        self.assertEqual(cooling.window_minutes(60), 1440)
        self.assertEqual(cooling.window_minutes(31), 1440)
        self.assertEqual(cooling.window_minutes(30), 120)
        self.assertEqual(cooling.window_minutes(8), 120)
        self.assertEqual(cooling.window_minutes(7), 30)
        self.assertEqual(cooling.window_minutes(0), 30)

    @override_settings(COOLING_OFF_SCHEME='flat')
    def test_the_flat_scheme_gives_everyone_the_same(self):
        for days in (0, 7, 8, 30, 31, 400):
            self.assertEqual(cooling.window_minutes(days), 30)

    @override_settings(COOLING_OFF_SCHEME='tiered')
    def test_a_booking_with_no_date_gets_the_most_generous_band(self):
        self.assertEqual(cooling.window_minutes(None), 1440)

    @override_settings(COOLING_OFF_SCHEME='nonsense')
    def test_an_unknown_scheme_falls_back_rather_than_crashing(self):
        """A typo in an env var must not stop bookings being taken."""
        self.assertEqual(cooling.active_scheme_name(), cooling.DEFAULT_SCHEME)
        self.assertIn(cooling.DEFAULT_SCHEME, cooling.SCHEMES)

    @override_settings(COOLING_OFF_SCHEME='')
    def test_an_unset_env_var_uses_the_one_default(self):
        """
        settings leaves this empty deliberately, so DEFAULT_SCHEME is the only
        answer to which scheme is running — including for cooling_sync.py,
        which reads this module without Django.
        """
        self.assertEqual(cooling.active_scheme_name(), cooling.DEFAULT_SCHEME)

    def test_every_scheme_ends_in_a_band_that_matches_any_booking(self):
        """A last band above 0 days would leave near bookings with no window."""
        for name, scheme in cooling.SCHEMES.items():
            self.assertEqual(scheme['bands'][-1]['min_days'], 0, name)

    def test_every_scheme_is_described_in_both_languages(self):
        keys = {'headline', 'sentence', 'detail', 'parenthetical', 'rows'}
        for name, scheme in cooling.SCHEMES.items():
            for lang in ('en', 'ru'):
                self.assertIn(lang, scheme['text'], name)
                self.assertEqual(keys, set(scheme['text'][lang]), f'{name}/{lang}')


class SchemeReachesBookingsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guide = User.objects.create_user(email='g@example.com', password='x',
                                             role=User.Role.OPERATOR)
        cls.traveller = User.objects.create_user(email='t@example.com', password='x')
        cls.tour = Tour.objects.create(operator=cls.guide, title='Ushba', country='Georgia',
                                       destination='Mestia', price_adult=Decimal('500'),
                                       currency='USD', status=Tour.Status.LIVE, max_group=8)

    def _book(self, days_out=60):
        start = date.today() + timedelta(days=days_out)
        dep = DepartureDate.objects.create(tour=self.tour, start_date=start,
                                           end_date=start + timedelta(days=3),
                                           spots_total=8, spots_left=8)
        client = APIClient()
        client.force_authenticate(self.traveller)
        res = client.post('/api/v1/bookings/', {
            'tour_slug': self.tour.slug, 'departure_id': dep.pk,
            'adults': 1, 'children': 0,
            'first_name': 'A', 'last_name': 'B', 'email': 't@example.com',
            'phone': '+70000000000', 'country': 'GE',
        }, format='json')
        self.assertIn(res.status_code, (200, 201), res.data)
        return Booking.objects.get(pk=res.data['id'])

    @override_settings(COOLING_OFF_SCHEME='tiered')
    def test_a_distant_booking_gets_a_day_under_the_tiered_scheme(self):
        bk = self._book(days_out=60)
        mins = round((bk.cooling_off_until - bk.created_at).total_seconds() / 60)
        self.assertAlmostEqual(mins, 1440, delta=2)

    @override_settings(COOLING_OFF_SCHEME='flat')
    def test_the_same_booking_gets_thirty_minutes_under_the_flat_scheme(self):
        bk = self._book(days_out=60)
        mins = round((bk.cooling_off_until - bk.created_at).total_seconds() / 60)
        self.assertAlmostEqual(mins, 30, delta=2)


class CaptureTimingFollowsSchemeTest(TestCase):
    """
    One setting decides both the window and how the money is held, because the
    two are one decision: a long window makes charge-then-refund expensive, a
    short one makes deferring more machinery than it saves.
    """

    @override_settings(COOLING_OFF_SCHEME='tiered')
    def test_the_long_window_holds_the_card(self):
        self.assertTrue(cooling.defers_capture())

    @override_settings(COOLING_OFF_SCHEME='flat')
    def test_the_short_window_charges_at_booking(self):
        self.assertFalse(cooling.defers_capture())

    @override_settings(COOLING_OFF_SCHEME='flat')
    def test_nothing_defers_under_the_flat_scheme_even_on_a_capable_rail(self):
        """
        Switching scheme must be enough on its own. If a registered rail could
        still defer, flipping to flat would leave authorisations outstanding
        with no window left to wait for.
        """
        from datetime import timedelta
        from django.utils import timezone
        from apps.payments import capture as cap
        from apps.bookings.models import Booking

        cap.register('stripe', lambda bk: None, lambda bk: None)
        try:
            bk = Booking(payment_method='stripe',
                         capture_status=Booking.Capture.NONE,
                         cooling_off_until=timezone.now() + timedelta(hours=5))
            self.assertFalse(cap.should_defer_capture(bk))
        finally:
            cap._HANDLERS.pop('stripe', None)
            cap.CAPTURE_CAPABLE_METHODS.discard('stripe')

    def test_every_scheme_says_which_way_it_holds_money(self):
        for name, scheme in cooling.SCHEMES.items():
            self.assertIn('defers_capture', scheme, name)


class PolicyEndpointTest(TestCase):

    @override_settings(COOLING_OFF_SCHEME='flat')
    def test_the_pages_are_told_which_scheme_is_running(self):
        res = APIClient().get('/api/v1/bookings/cooling-off/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['scheme'], 'flat')
        self.assertIn('30 minutes', res.data['text']['en']['headline'])
        self.assertIn('30 минут', res.data['text']['ru']['headline'])

    def test_it_does_not_need_a_login(self):
        """The tour and terms pages describe the window before anyone signs in."""
        self.assertEqual(APIClient().get('/api/v1/bookings/cooling-off/').status_code, 200)
