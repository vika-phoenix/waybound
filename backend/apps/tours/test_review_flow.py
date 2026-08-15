"""
What a guide is told between submitting a tour and it going live.

Both admin actions used to be bare `queryset.update()` calls: the tour went
live, or dropped back to draft, and the person who wrote it was told nothing.
A guide had to keep opening the dashboard to find out, and a rejection carried
no reason, so they resubmitted the same thing or gave up.

The rule these lock in: a notice may never undo the transition it describes. An
admin who approves a tour must not see an error because a mail server was down.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core import mail
from django.test import RequestFactory, TestCase

from apps.tours.admin import TourAdmin
from apps.tours.models import Tour
from apps.users.models import User


class TourReviewNoticesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(email='admin@example.com', password='x')
        cls.guide = User.objects.create_user(
            email='guide@example.com', password='x', role=User.Role.OPERATOR,
            first_name='Nino', is_verified=True)
        cls.tour = Tour.objects.create(
            operator=cls.guide, title='Svaneti High Route', country='Georgia',
            destination='Mestia', price_adult=Decimal('500'), currency='USD',
            status=Tour.Status.REVIEW, max_group=8)

    def setUp(self):
        self.site = TourAdmin(Tour, AdminSite())
        self.rf = RequestFactory()
        mail.outbox = []

    def _request(self, post=None):
        req = self.rf.post('/admin/tours/tour/', post or {})
        req.user = self.admin_user
        # The reject page renders through each_context, which reads messages.
        req.session = SessionStore()
        req._messages = FallbackStorage(req)
        return req

    # ── approval ─────────────────────────────────────────────────────────────

    def test_publishing_tells_the_guide_and_links_the_tour(self):
        self.site.publish_tours(self._request(), Tour.objects.filter(pk=self.tour.pk))

        self.tour.refresh_from_db()
        self.assertEqual(self.tour.status, Tour.Status.LIVE)
        self.assertIsNotNone(self.tour.published_at)

        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ['guide@example.com'])
        self.assertIn('Svaneti High Route', msg.subject)
        self.assertIn(self.tour.slug, msg.body)
        self.assertIn('Nino', msg.body)

    def test_a_dead_mail_server_cannot_undo_a_publish(self):
        with patch('apps.tours.emails.send_mail', side_effect=Exception('smtp down')):
            self.site.publish_tours(self._request(), Tour.objects.filter(pk=self.tour.pk))
        self.tour.refresh_from_db()
        self.assertEqual(self.tour.status, Tour.Status.LIVE,
                         'the tour is live; the notice failing is a separate problem')

    # ── rejection ────────────────────────────────────────────────────────────

    def test_rejecting_asks_for_a_reason_before_changing_anything(self):
        resp = self.site.reject_tours(self._request(), Tour.objects.filter(pk=self.tour.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('What needs changing', resp.content.decode())

        self.tour.refresh_from_db()
        self.assertEqual(self.tour.status, Tour.Status.REVIEW,
                         'the prompt must not send the tour back on its own')
        self.assertEqual(len(mail.outbox), 0)

    def test_the_reason_reaches_the_guide_word_for_word(self):
        reason = 'The itinerary stops at day 4 of 6, and all six photos are the same viewpoint.'
        self.site.reject_tours(self._request({'apply': '1', 'reason': reason}),
                               Tour.objects.filter(pk=self.tour.pk))

        self.tour.refresh_from_db()
        self.assertEqual(self.tour.status, Tour.Status.DRAFT)

        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn(reason, body)
        self.assertIn('still there', body, 'the guide needs to know nothing was lost')
        self.assertIn(self.tour.slug, body, 'and a link back to the editor')

    def test_a_rejection_with_no_reason_still_says_something_useful(self):
        """An empty box must not produce an email that explains nothing."""
        self.site.reject_tours(self._request({'apply': '1', 'reason': '   '}),
                               Tour.objects.filter(pk=self.tour.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Reply to this email', mail.outbox[0].body)

    # ── the API path an admin might use instead ──────────────────────────────

    def test_approving_through_the_api_notifies_too(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(self.admin_user)
        r = client.patch(f'/api/v1/tours/{self.tour.slug}/publish/')
        self.assertEqual(r.status_code, 200)
        self.tour.refresh_from_db()
        self.assertEqual(self.tour.status, Tour.Status.LIVE)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('is live', mail.outbox[0].subject)

class PublishValidationTest(TestCase):
    """
    The completeness rules ran only in the dashboard's JavaScript, so they were
    advice. A direct API call — or a page whose script failed to load — could
    push a half-empty tour into the review queue for a human to reject by hand.
    """

    @classmethod
    def setUpTestData(cls):
        cls.guide = User.objects.create_user(
            email='pub@example.com', password='x', role=User.Role.OPERATOR,
            is_verified=True)

    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.client.force_authenticate(self.guide)

    def _bare_tour(self):
        return Tour.objects.create(
            operator=self.guide, title='Untitled tour', status=Tour.Status.DRAFT,
            price_adult=Decimal('0'), max_group=0)

    def _complete_tour(self):
        from datetime import date, timedelta
        from apps.tours.models import DayItinerary, DepartureDate, TourPhoto
        t = Tour.objects.create(
            operator=self.guide, title='Kazbegi Traverse', country='Georgia',
            destination='Stepantsminda', difficulty='moderate',
            categories=['Trekking'], price_adult=Decimal('500'), max_group=8,
            description='<p>Six days across the Kazbegi massif.</p>',
            status=Tour.Status.DRAFT)
        start = date.today() + timedelta(days=40)
        DepartureDate.objects.create(tour=t, start_date=start,
                                     end_date=start + timedelta(days=5),
                                     spots_total=8, spots_left=8)
        DayItinerary.objects.create(tour=t, day_number=1, title='Arrive in Stepantsminda')
        for i in range(3):
            TourPhoto.objects.create(tour=t, image=f'tours/x{i}.jpg')
        return t

    def test_an_empty_tour_cannot_reach_the_review_queue(self):
        t = self._bare_tour()
        r = self.client.patch(f'/api/v1/tours/{t.slug}/publish/')
        self.assertEqual(r.status_code, 400)
        t.refresh_from_db()
        self.assertEqual(t.status, Tour.Status.DRAFT)

    def test_the_response_names_every_missing_piece(self):
        r = self.client.patch(f'/api/v1/tours/{self._bare_tour().slug}/publish/')
        missing = r.data['missing']
        # Difficulty is deliberately absent: the model defaults it to
        # 'moderate', so it can never be blank. The dashboard checks for it too
        # and that check is equally unreachable.
        for expected in ['Tour name', 'Category (select at least one)',
                         'Country', 'Destination / city', 'Max group size',
                         'Full tour description', 'At least 1 departure date',
                         'At least 1 itinerary day with a title']:
            self.assertIn(expected, missing)
        self.assertTrue(any('At least 3 photos' in m for m in missing))

    def test_a_complete_tour_still_submits(self):
        t = self._complete_tour()
        r = self.client.patch(f'/api/v1/tours/{t.slug}/publish/')
        self.assertEqual(r.status_code, 200, getattr(r, 'data', None))
        t.refresh_from_db()
        self.assertEqual(t.status, Tour.Status.REVIEW)

    def test_two_photos_is_not_three(self):
        t = self._complete_tour()
        t.photos.first().delete()
        r = self.client.patch(f'/api/v1/tours/{t.slug}/publish/')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(any('currently: 2' in m for m in r.data['missing']))

    def test_an_editor_leftover_is_not_a_description(self):
        """The rich-text editor leaves <p></p> behind, which is not empty."""
        t = self._complete_tour()
        t.description = '<p><br></p>'
        t.save(update_fields=['description'])
        r = self.client.patch(f'/api/v1/tours/{t.slug}/publish/')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Full tour description', r.data['missing'])

    def test_an_untitled_itinerary_day_does_not_count(self):
        t = self._complete_tour()
        t.itinerary.update(title='')
        r = self.client.patch(f'/api/v1/tours/{t.slug}/publish/')
        self.assertEqual(r.status_code, 400)
        self.assertIn('At least 1 itinerary day with a title', r.data['missing'])

    def test_an_admin_publishing_is_not_blocked_by_this(self):
        """
        The gate is on submission, not approval. An admin looking at a tour has
        already judged it; the rules exist to keep the queue clean.
        """
        admin = User.objects.create_superuser(email='adm2@example.com', password='x')
        t = self._bare_tour()
        t.status = Tour.Status.REVIEW
        t.save(update_fields=['status'])
        self.client.force_authenticate(admin)
        r = self.client.patch(f'/api/v1/tours/{t.slug}/publish/')
        self.assertEqual(r.status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.status, Tour.Status.LIVE)
