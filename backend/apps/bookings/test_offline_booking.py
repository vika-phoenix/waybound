"""
Booking someone in by hand, and reading messages as conversations.

Both go through the real admin request path rather than calling the helpers
directly — a view nobody can reach is not a feature, and that mistake has been
made on this admin before.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core import mail
from django.test import TestCase

from apps.bookings.models import Booking, EnquiryMessage, EnquiryReply
from apps.tours.models import DepartureDate, Tour
from apps.users.models import User

URL = '/admin/bookings/booking/offline/'


class OfflineBookingAdminTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(email='admin@example.com', password='x')
        cls.guide = User.objects.create_user(email='guide@example.com', password='x',
                                             role=User.Role.OPERATOR)
        cls.tour = Tour.objects.create(operator=cls.guide, title='Svaneti Traverse',
                                       country='Georgia', destination='Mestia',
                                       price_adult=Decimal('600'), currency='USD',
                                       status=Tour.Status.LIVE, max_group=8)
        start = date.today() + timedelta(days=40)
        cls.dep = DepartureDate.objects.create(tour=cls.tour, start_date=start,
                                               end_date=start + timedelta(days=5),
                                               spots_total=8, spots_left=8)

    def setUp(self):
        self.client.force_login(self.admin)
        mail.outbox = []

    def _post(self, **over):
        data = {
            'tour': self.tour.pk, 'departure': self.dep.pk,
            'first_name': 'Marta', 'last_name': 'Ilves',
            'email': 'marta@example.com', 'phone': '+372 5000 000', 'country': 'Estonia',
            'adults': 2, 'children': 0, 'infants': 0,
            'amount_received': '1200.00', 'how_paid': 'SEPA 14 Aug', 'notes': '',
            'notify': 'on',
        }
        data.update(over)
        return self.client.post(URL, data, follow=True)

    # ── Reachable ───────────────────────────────────────────────────────────

    def test_the_booking_list_links_to_it(self):
        r = self.client.get('/admin/bookings/booking/')
        self.assertContains(r, URL)

    def test_the_form_renders(self):
        r = self.client.get(URL)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'amount_received')

    # ── What it creates ─────────────────────────────────────────────────────

    def test_it_creates_a_confirmed_paid_booking(self):
        self._post()
        bk = Booking.objects.get(email='marta@example.com')
        self.assertEqual(bk.status, Booking.Status.CONFIRMED)
        self.assertEqual(bk.deposit_status, 'paid')
        self.assertEqual(bk.deposit_paid, Decimal('1200.00'))
        self.assertEqual(bk.payment_method, 'bank')
        self.assertEqual(bk.total_price, Decimal('1200'),
                         'prices must come from the tour, not be typed in')

    def test_the_seats_come_off_the_departure(self):
        self._post()
        self.dep.refresh_from_db()
        self.assertEqual(self.dep.spots_left, 6,
                         'an offline booking takes real seats or it overbooks the trip')

    def test_the_commission_is_snapshotted(self):
        """Otherwise a later rate change silently rewrites what this guide is owed."""
        self._post()
        bk = Booking.objects.get(email='marta@example.com')
        self.assertIsNotNone(bk.commission_pct)
        self.assertGreater(bk.payout_amount, 0)

    def test_the_cancellation_policy_is_snapshotted(self):
        self._post()
        bk = Booking.objects.get(email='marta@example.com')
        self.assertTrue(bk.cancel_policy_snapshot,
                        'the traveller must be on the same terms as anyone else')

    def test_it_attaches_to_an_existing_account(self):
        traveller = User.objects.create_user(email='marta@example.com', password='x')
        self._post()
        bk = Booking.objects.get(email='marta@example.com')
        self.assertEqual(bk.tourist_id, traveller.pk,
                         'the booking should appear in their My bookings')

    def test_how_it_was_paid_is_recorded(self):
        self._post()
        bk = Booking.objects.get(email='marta@example.com')
        self.assertIn('SEPA 14 Aug', bk.notes)

    def test_zero_received_holds_the_place_without_confirming_it(self):
        self._post(amount_received='0')
        bk = Booking.objects.get(email='marta@example.com')
        self.assertEqual(bk.status, Booking.Status.PENDING)
        self.assertEqual(bk.deposit_status, 'pending')
        self.dep.refresh_from_db()
        self.assertEqual(self.dep.spots_left, 8,
                         'no money, no seat held')

    # ── Who hears about it ──────────────────────────────────────────────────

    def test_both_sides_are_emailed(self):
        self._post()
        to = [addr for m in mail.outbox for addr in m.to]
        self.assertIn('marta@example.com', to)
        self.assertIn('guide@example.com', to)

    def test_the_emails_can_be_suppressed(self):
        data_without_notify = {'notify': ''}
        self._post(**data_without_notify)
        self.assertEqual(mail.outbox, [])

    # ── What it refuses ─────────────────────────────────────────────────────

    def test_it_will_not_overbook_a_departure(self):
        self.dep.spots_left = 1
        self.dep.save(update_fields=['spots_left'])
        r = self._post()
        self.assertContains(r, 'Only 1 seat')
        self.assertFalse(Booking.objects.filter(email='marta@example.com').exists())

    def test_it_will_not_exceed_the_group_maximum(self):
        r = self._post(adults=20)
        self.assertContains(r, 'maximum group')
        self.assertFalse(Booking.objects.filter(email='marta@example.com').exists())

    def test_a_departure_from_another_tour_is_refused(self):
        other = Tour.objects.create(operator=self.guide, title='Other', country='Georgia',
                                    destination='X', price_adult=Decimal('100'),
                                    currency='USD', status=Tour.Status.LIVE, max_group=8)
        start = date.today() + timedelta(days=60)
        other_dep = DepartureDate.objects.create(tour=other, start_date=start,
                                                 end_date=start + timedelta(days=2),
                                                 spots_total=4, spots_left=4)
        r = self._post(departure=other_dep.pk)
        self.assertContains(r, 'belongs to')
        self.assertFalse(Booking.objects.filter(email='marta@example.com').exists())


class MessagesAdminTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(email='admin@example.com', password='x')
        cls.guide = User.objects.create_user(email='guide@example.com', password='x',
                                             role=User.Role.OPERATOR)
        cls.traveller = User.objects.create_user(email='t@example.com', password='x')
        cls.tour = Tour.objects.create(operator=cls.guide, title='Kazbek Ascent',
                                       country='Georgia', destination='Stepantsminda',
                                       price_adult=Decimal('900'), currency='USD',
                                       status=Tour.Status.LIVE, max_group=8)
        cls.clean = EnquiryMessage.objects.create(
            tour=cls.tour, sender=cls.traveller, name='Tom', email='t@example.com',
            message='Is there a hut on the second night?')
        cls.leaky = EnquiryMessage.objects.create(
            tour=cls.tour, name='Ann', email='a@example.com',
            message='Easier to talk on whatsapp, +995 555 123 456')

    def setUp(self):
        self.client.force_login(self.admin)

    def test_the_enquiry_list_links_to_the_thread_view(self):
        r = self.client.get('/admin/bookings/enquirymessage/')
        self.assertContains(r, '/admin/bookings/enquirymessage/threads/')

    def test_threads_shows_the_whole_conversation(self):
        EnquiryReply.objects.create(enquiry=self.clean, sender=self.guide,
                                    is_operator=True, body='Yes, a stone hut.')
        r = self.client.get('/admin/bookings/enquirymessage/threads/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Is there a hut on the second night?')
        self.assertContains(r, 'Yes, a stone hut.',
                            msg_prefix='replies live in another table and used to be invisible')

    def test_contact_details_are_flagged(self):
        r = self.client.get('/admin/bookings/enquirymessage/threads/')
        body = r.content.decode()
        self.assertIn('1 flagged', body)
        self.assertIn('carrying what look like contact details', body)

    def test_the_message_itself_is_never_rewritten(self):
        r = self.client.get('/admin/bookings/enquirymessage/threads/')
        self.assertContains(r, '+995 555 123 456',
                            msg_prefix='flagging must not destroy what was written')

    def test_flagged_only_filters(self):
        r = self.client.get('/admin/bookings/enquirymessage/threads/?flagged=1')
        body = r.content.decode()
        self.assertIn('whatsapp', body)
        self.assertNotIn('Is there a hut on the second night?', body)

    def test_search_narrows_by_text(self):
        r = self.client.get('/admin/bookings/enquirymessage/threads/?q=hut')
        body = r.content.decode()
        self.assertIn('Is there a hut', body)
        self.assertNotIn('whatsapp', body)

    def test_a_reply_flag_counts_too(self):
        EnquiryReply.objects.create(enquiry=self.clean, sender=self.guide, is_operator=True,
                                    body='Call me on +995 599 111 222')
        r = self.client.get('/admin/bookings/enquirymessage/threads/?flagged=1')
        self.assertContains(r, 'Is there a hut',
                            msg_prefix='a clean opening message with a leaky reply is still a leak')

    def test_a_booked_traveller_is_marked_as_such(self):
        """
        The flag only means anything before a booking — afterwards both sides
        can see each other's details anyway.
        """
        bk = Booking.objects.create(
            tour=self.tour, tourist=self.traveller, adults=1,
            first_name='Tom', last_name='X', email='t@example.com',
            price_adult=Decimal('900'), total_price=Decimal('900'), currency='USD',
            status=Booking.Status.CONFIRMED)
        r = self.client.get('/admin/bookings/enquirymessage/threads/')
        self.assertContains(r, bk.reference)
        self.assertContains(r, 'No booking',
                            msg_prefix='the unbooked enquirer should still read as unbooked')
