"""
What a stranger is allowed to see when someone left their name blank.

first_name and last_name are optional on the model, and full_name falls back
to the email address. That fallback is right in an admin column and in our own
alerts, and it was also being rendered on tour pages and under reviews — so a
guide who skipped their name had a personal email address on every listing,
and a traveller who skipped theirs had one printed under their review.
"""
from decimal import Decimal

from django.test import TestCase

from apps.tours.models import Tour
from apps.users.models import User


class PublicDisplayNameTest(TestCase):

    def test_a_named_person_is_shown_by_name(self):
        u = User.objects.create_user(email='a@example.com', password='x',
                                     first_name='Nino', last_name='Beridze')
        self.assertEqual(u.public_display_name, 'Nino Beridze')

    def test_a_nameless_guide_never_leaks_their_email(self):
        u = User.objects.create_user(email='guide@example.com', password='x',
                                     role=User.Role.OPERATOR)
        self.assertNotIn('@', u.public_display_name)
        self.assertEqual(u.public_display_name, 'Kavkazland Guide')

    def test_a_nameless_traveller_never_leaks_their_email(self):
        u = User.objects.create_user(email='t@example.com', password='x')
        self.assertNotIn('@', u.public_display_name)

    def test_full_name_keeps_the_email_for_staff_screens(self):
        """The fallback is useful internally — it just must not reach a page."""
        u = User.objects.create_user(email='ops@example.com', password='x')
        self.assertEqual(u.full_name, 'ops@example.com')


class GuideNameIsAPublishGateTest(TestCase):

    def test_a_tour_cannot_go_live_showing_a_placeholder_for_the_guide(self):
        from apps.tours.views import incomplete_tour_fields

        guide = User.objects.create_user(email='g@example.com', password='x',
                                         role=User.Role.OPERATOR)
        tour = Tour.objects.create(operator=guide, title='Ushba', country='Georgia',
                                   destination='Mestia', price_adult=Decimal('500'),
                                   currency='USD', max_group=8)
        missing = incomplete_tour_fields(tour)
        self.assertIn('Your name (Settings → Profile)', missing)

        guide.first_name, guide.last_name = 'Nino', 'Beridze'
        guide.save(update_fields=['first_name', 'last_name'])
        tour.operator.refresh_from_db()
        self.assertNotIn('Your name (Settings → Profile)',
                         incomplete_tour_fields(Tour.objects.get(pk=tour.pk)))


class BioIsAPublishGateNotASaveGateTest(TestCase):
    """
    "About you" was enforced in the settings page's save handler, which had it
    backwards twice: a guide could not correct their phone number until they
    had written a bio, and a direct API call skipped the check entirely.
    """

    def setUp(self):
        self.guide = User.objects.create_user(
            email='g2@example.com', password='x', role=User.Role.OPERATOR,
            first_name='Nino', last_name='Beridze', avatar='avatars/x.jpg')
        self.tour = Tour.objects.create(
            operator=self.guide, title='Ushba', country='Georgia',
            destination='Mestia', price_adult=Decimal('500'), currency='USD',
            max_group=8)

    def test_publishing_asks_for_it(self):
        from apps.tours.views import incomplete_tour_fields
        self.assertTrue(any('About you' in m for m in incomplete_tour_fields(self.tour)))

    def test_saving_the_profile_does_not(self):
        """Changing a phone number must not require writing a bio first."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(self.guide)
        res = client.patch('/api/v1/auth/me/', {'phone': '+995555000111'}, format='json')
        self.assertIn(res.status_code, (200, 202), getattr(res, 'data', None))
        self.guide.refresh_from_db()
        self.assertEqual(self.guide.phone, '+995555000111')
        self.assertEqual(self.guide.bio, '')


class PublicSerialisersTest(TestCase):

    def test_the_tour_page_shows_no_email_for_a_nameless_guide(self):
        from apps.tours.serializers import TourListSerializer

        guide = User.objects.create_user(email='secret@example.com', password='x',
                                         role=User.Role.OPERATOR)
        tour = Tour.objects.create(operator=guide, title='Ushba', country='Georgia',
                                   destination='Mestia', price_adult=Decimal('500'),
                                   currency='USD', max_group=8, status=Tour.Status.LIVE)
        data = TourListSerializer(tour).data
        self.assertNotIn('secret@example.com', str(data))
