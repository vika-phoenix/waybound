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