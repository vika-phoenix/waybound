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

from django.test import TestCase

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