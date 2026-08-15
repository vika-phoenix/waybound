"""
Booking access rules.

These lock in one invariant that is easy to break by accident: **booking is
gated on being logged in, never on role.**

`role` is a single field, so a traveller who becomes a guide has their role
overwritten. That is safe today precisely because nothing checks for
`role == 'tourist'` before letting someone book. Adding such a check reads as
obviously correct in isolation — tourists book, operators sell — but it would
strip every upgraded user of the ability to book, with no error at upgrade
time. The breakage surfaces later, in a different feature, for a subset of
users. test_operator_can_book_another_operators_tour is here to fail loudly
the moment someone adds that check.

The one restriction that IS intended: you cannot book your own tour.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.bookings.models import Booking
from apps.bookings.serializers import BookingCreateSerializer
from apps.tours.models import DepartureDate, Tour
from apps.users.models import User


class _Req:
    """Minimal stand-in for the request the serializer reads off the context."""

    def __init__(self, user):
        self.user = user


class BookingAccessRulesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email='owner@example.com', password='x', role=User.Role.OPERATOR)
        cls.other_guide = User.objects.create_user(
            email='guide@example.com', password='x', role=User.Role.OPERATOR)
        cls.tourist = User.objects.create_user(
            email='tourist@example.com', password='x', role=User.Role.TOURIST)

        cls.tour = Tour.objects.create(
            operator=cls.owner, title='Elbrus Traverse', country='Russia',
            destination='Mount Elbrus', price_adult=Decimal('500.00'),
            status=Tour.Status.LIVE, max_group=10,
        )
        start = date.today() + timedelta(days=60)
        cls.departure = DepartureDate.objects.create(
            tour=cls.tour, start_date=start, end_date=start + timedelta(days=5),
            spots_total=10, spots_left=10,
        )

    def _payload(self):
        return {
            'tour_slug': self.tour.slug,
            'adults': 1,
            'children': 0,
            'first_name': 'Test',
            'last_name': 'Booker',
            'email': 'booker@example.com',
            'phone': '+70000000000',
            'departure_date': str(self.departure.start_date),
            'departure_id': self.departure.id,
        }

    def _validate_as(self, user):
        s = BookingCreateSerializer(data=self._payload(),
                                    context={'request': _Req(user)})
        return s.is_valid(), s.errors

    def test_tourist_can_book(self):
        valid, errors = self._validate_as(self.tourist)
        self.assertTrue(valid, f'tourist should be able to book: {errors}')

    def test_operator_can_book_another_operators_tour(self):
        """
        A guide is also a traveller. If this fails, someone has gated booking on
        role — see the module docstring before "fixing" this test.
        """
        valid, errors = self._validate_as(self.other_guide)
        self.assertTrue(
            valid,
            'Booking must not be gated on role. An operator has to be able to '
            f'book somebody else\'s tour. Errors: {errors}',
        )

    def test_operator_cannot_book_own_tour(self):
        valid, errors = self._validate_as(self.owner)
        self.assertFalse(valid, 'owner should not be able to book their own tour')
        self.assertIn('cannot book your own tour',
                      str(errors.get('non_field_errors', errors)))

    def test_upgrading_a_tourist_to_guide_keeps_them_able_to_book(self):
        """The upgrade path itself: role flips, booking still works."""
        self.tourist.role = User.Role.OPERATOR
        self.tourist.save(update_fields=['role'])
        valid, errors = self._validate_as(self.tourist)
        self.assertTrue(
            valid,
            f'upgrading a traveller to guide must not cost them booking: {errors}',
        )

class CommissionLedgerTest(TestCase):
    """
    Every number a guide or an admin sees comes off these four properties, so
    they carry the whole promise: "15% commission, you keep the rest".

    The base is what was *kept*, not total_price. That one choice makes the
    deposit-only case, the late cancellation that kept a penalty, and the full
    refund all fall out of the same arithmetic — and a fully refunded booking
    correctly owes nobody anything.
    """

    @classmethod
    def setUpTestData(cls):
        cls.guide = User.objects.create_user(
            email='ledger-guide@example.com', password='x', role=User.Role.OPERATOR)
        cls.tour = Tour.objects.create(
            operator=cls.guide, title='Ledger Tour', country='Georgia',
            destination='Kazbegi', price_adult=Decimal('500.00'),
            currency='USD', status=Tour.Status.LIVE, max_group=10)

    def _bk(self, **kw):
        defaults = dict(
            tour=self.tour, first_name='A', last_name='B', email='a@b.com',
            adults=2, currency='USD', price_adult=Decimal('500.00'),
            total_price=Decimal('1000.00'), status=Booking.Status.COMPLETED,
        )
        defaults.update(kw)
        return Booking(**defaults)

    def test_paid_in_full(self):
        b = self._bk(deposit_paid=Decimal('300'), balance_paid=Decimal('700'),
                     commission_pct=Decimal('15'))
        self.assertEqual(b.amount_collected, 1000.00)
        self.assertEqual(b.commission_amount, 150.00)
        self.assertEqual(b.payout_amount, 850.00)

    def test_deposit_only_owes_only_on_the_deposit(self):
        """The guide is not owed a share of money nobody has paid yet."""
        b = self._bk(deposit_paid=Decimal('300'), commission_pct=Decimal('15'))
        self.assertEqual(b.commission_amount, 45.00)
        self.assertEqual(b.payout_amount, 255.00)

    def test_full_refund_owes_nobody(self):
        b = self._bk(deposit_paid=Decimal('1000'), refund_amount=Decimal('1000'),
                     status=Booking.Status.CANCELLED, commission_pct=Decimal('15'))
        self.assertEqual(b.amount_kept, 0.00)
        self.assertEqual(b.commission_amount, 0.00)
        self.assertEqual(b.payout_amount, 0.00)

    def test_cancellation_penalty_is_split_like_anything_else(self):
        """
        $1000 paid, $600 refunded, $400 kept. The platform takes its cut of the
        $400 — the card fee on the original charge is not refunded either.
        """
        b = self._bk(deposit_paid=Decimal('1000'), refund_amount=Decimal('600'),
                     status=Booking.Status.CANCELLED, commission_pct=Decimal('15'))
        self.assertEqual(b.amount_kept, 400.00)
        self.assertEqual(b.commission_amount, 60.00)
        self.assertEqual(b.payout_amount, 340.00)

    def test_a_refund_larger_than_collected_never_goes_negative(self):
        b = self._bk(deposit_paid=Decimal('100'), refund_amount=Decimal('250'),
                     commission_pct=Decimal('15'))
        self.assertEqual(b.amount_kept, 0.00)
        self.assertEqual(b.payout_amount, 0.00)

    @override_settings(PLATFORM_COMMISSION_PCT=15.0)
    def test_the_rate_is_frozen_on_first_payment(self):
        """
        The whole reason the rate is a column and not a settings lookup: raising
        the platform rate must not retroactively cut what an existing guide is
        owed.
        """
        b = self._bk(deposit_paid=Decimal('1000'))
        b.save()
        b.snapshot_commission()
        b.refresh_from_db()
        self.assertEqual(b.commission_pct, Decimal('15.00'))
        self.assertEqual(b.payout_amount, 850.00)

        with override_settings(PLATFORM_COMMISSION_PCT=25.0):
            b.refresh_from_db()
            self.assertEqual(b.payout_amount, 850.00,
                             'a rate change must not rewrite a booking already paid')
            self.assertFalse(b.snapshot_commission(), 'snapshot must be idempotent')
            b.refresh_from_db()
            self.assertEqual(b.commission_pct, Decimal('15.00'))

    @override_settings(PLATFORM_COMMISSION_PCT=15.0)
    def test_a_negotiated_rate_beats_the_platform_default(self):
        self.guide.commission_pct_override = Decimal('10.00')
        self.guide.save(update_fields=['commission_pct_override'])
        b = self._bk(deposit_paid=Decimal('1000'))
        b.save()
        b.snapshot_commission()
        self.assertEqual(b.commission_pct, Decimal('10.00'))
        self.assertEqual(b.payout_amount, 900.00)

    @override_settings(PLATFORM_COMMISSION_PCT=15.0)
    def test_an_unpaid_booking_falls_back_to_todays_rate_for_display(self):
        b = self._bk(deposit_paid=Decimal('0'), status=Booking.Status.PENDING)
        self.assertIsNone(b.commission_pct)
        self.assertEqual(b.effective_commission_pct, 15.0)
        self.assertEqual(b.payout_amount, 0.00)

    def test_the_split_is_not_exposed_to_travellers(self):
        """A traveller must never see what the guide is paid."""
        from apps.bookings.serializers import BookingDetailSerializer
        leaky = {'commission_pct', 'commission_amount', 'payout_amount',
                 'amount_kept', 'payout_status', 'payout_reference'}
        exposed = set(BookingDetailSerializer.Meta.fields) & leaky
        self.assertFalse(exposed, f'tourist serializer exposes {exposed}')

    def test_the_free_window_deadline_reaches_the_bookings_page(self):
        """
        My bookings shows the policy snapshot, which describes what happens
        after the window shuts. Without the deadline itself the page tells
        someone inside the window they would lose money, which is wrong.
        """
        from apps.bookings.serializers import BookingDetailSerializer
        self.assertIn('cooling_off_until', BookingDetailSerializer.Meta.fields)
