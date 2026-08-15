"""Prove the payout admin is reachable and renders, not just that it imports."""
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, override_settings
from apps.bookings.models import Booking
from apps.tours.models import DepartureDate, Tour
from apps.users.models import User


class PayoutAdminTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(email='admin@example.com', password='x')
        cls.guide = User.objects.create_user(email='g@example.com', password='x',
                                             role=User.Role.OPERATOR, payout_name='G Guide',
                                             payout_bank='Bank', payout_account='123')
        cls.tour = Tour.objects.create(operator=cls.guide, title='T', country='Georgia',
                                       destination='K', price_adult=Decimal('500'),
                                       currency='USD', status=Tour.Status.LIVE, max_group=8)
        start = date.today() - timedelta(days=10)
        cls.dep = DepartureDate.objects.create(tour=cls.tour, start_date=start,
                                               end_date=start + timedelta(days=3),
                                               spots_total=8, spots_left=6)
        cls.bk = Booking.objects.create(
            tour=cls.tour, departure=cls.dep, departure_date=start, adults=2,
            first_name='A', last_name='B', email='a@b.com', currency='USD',
            price_adult=Decimal('500'), total_price=Decimal('1000'),
            deposit_paid=Decimal('1000'), status=Booking.Status.COMPLETED,
            commission_pct=Decimal('15'), payout_status='due')

    def setUp(self):
        self.client.force_login(self.admin)

    def test_changelist_links_to_payouts_and_counts_them(self):
        r = self.client.get('/admin/bookings/booking/')
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('/admin/bookings/booking/payouts/', body)
        self.assertIn('1 booking awaiting payout', body)

    def test_payouts_page_shows_who_is_owed_what(self):
        r = self.client.get('/admin/bookings/booking/payouts/')
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('g@example.com', body)
        self.assertIn('850.00', body)   # 1000 kept - 15%
        self.assertIn('150.00', body)   # commission

    def test_payouts_page_flags_a_guide_with_no_bank_details(self):
        self.guide.payout_name = ''
        self.guide.payout_account = ''
        self.guide.save(update_fields=['payout_name', 'payout_account'])
        r = self.client.get('/admin/bookings/booking/payouts/')
        self.assertIn('cannot be paid yet', r.content.decode())

    def test_mark_payout_sent_asks_for_a_reference_then_records_it(self):
        confirm = self.client.post('/admin/bookings/booking/', {
            'action': 'mark_payout_sent', '_selected_action': [str(self.bk.pk)]})
        self.assertEqual(confirm.status_code, 200)
        self.assertIn('Transfer reference', confirm.content.decode())
        self.bk.refresh_from_db()
        self.assertEqual(self.bk.payout_status, 'due', 'the prompt must not settle anything')

        done = self.client.post('/admin/bookings/booking/', {
            'action': 'mark_payout_sent', '_selected_action': [str(self.bk.pk)],
            'apply': '1', 'payout_reference': 'SEPA-9912'}, follow=True)
        self.assertEqual(done.status_code, 200)
        self.bk.refresh_from_db()
        self.assertEqual(self.bk.payout_status, 'paid')
        self.assertEqual(self.bk.payout_reference, 'SEPA-9912')
        self.assertIsNotNone(self.bk.payout_sent_at)

    def test_the_negotiated_rate_is_editable_on_the_guide(self):
        r = self.client.get(f'/admin/users/user/{self.guide.pk}/change/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('commission_pct_override', r.content.decode(),
                      'a rate you cannot see in admin is a code change, not a setting')

    # ── The exact thing the user hit: nothing is due, so nothing happens ──────

    def _pending_booking(self):
        """A confirmed booking on a trip that has not run — the normal state."""
        start = date.today() + timedelta(days=30)
        dep = DepartureDate.objects.create(tour=self.tour, start_date=start,
                                           end_date=start + timedelta(days=3),
                                           spots_total=8, spots_left=7)
        return Booking.objects.create(
            tour=self.tour, departure=dep, departure_date=start, adults=1,
            first_name='C', last_name='D', email='c@d.com', currency='USD',
            price_adult=Decimal('500'), total_price=Decimal('500'),
            deposit_paid=Decimal('500'), status=Booking.Status.CONFIRMED,
            commission_pct=Decimal('15'), payout_status='not_due')

    def test_action_on_a_not_due_booking_explains_why_instead_of_dead_ending(self):
        bk = self._pending_booking()
        r = self.client.post('/admin/bookings/booking/', {
            'action': 'mark_payout_sent', '_selected_action': [str(bk.pk)]})
        body = r.content.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn('None of these are due for payout yet', body)
        self.assertIn(bk.reference, body)
        self.assertIn('not marked completed yet', body)
        self.assertIn('Mark trips as completed', body,
                      'the page has to say what to do next')

    def test_payouts_page_lists_money_that_is_not_payable_yet(self):
        """
        With no completed trips the page used to be blank, which reads as
        broken. It has to show what is coming.
        """
        bk = self._pending_booking()
        Booking.objects.filter(pk=self.bk.pk).update(payout_status='paid')
        r = self.client.get('/admin/bookings/booking/payouts/')
        body = r.content.decode()
        self.assertIn('Nothing is owed right now', body)
        self.assertIn('Not payable yet', body)
        self.assertIn(bk.reference, body)
        self.assertIn('425.00', body)   # 500 kept - 15%

    def test_payouts_page_records_a_transfer_without_the_dropdown(self):
        r = self.client.get('/admin/bookings/booking/payouts/')
        self.assertIn(f'/admin/bookings/booking/payouts/record/{self.guide.pk}/USD/',
                      r.content.decode())

        url = f'/admin/bookings/booking/payouts/record/{self.guide.pk}/USD/'
        form = self.client.get(url)
        self.assertEqual(form.status_code, 200)
        self.assertIn('Transfer reference', form.content.decode())
        self.bk.refresh_from_db()
        self.assertEqual(self.bk.payout_status, 'due', 'opening the form settles nothing')

        done = self.client.post(url, {'apply': '1', 'payout_reference': 'WISE-3321'}, follow=True)
        self.assertEqual(done.status_code, 200)
        self.bk.refresh_from_db()
        self.assertEqual(self.bk.payout_status, 'paid')
        self.assertEqual(self.bk.payout_reference, 'WISE-3321')

    def test_the_action_labels_say_what_they_do_and_in_what_order(self):
        r = self.client.get('/admin/bookings/booking/')
        body = r.content.decode()
        self.assertIn('2. Mark trips as completed', body)
        self.assertIn('3. Record that I paid the guide', body)


class DocumentStorageBannerTest(TestCase):
    """
    The system check only prints into a deploy log. The person who cares about
    these files is looking at the documents page, so it has to say it there.
    """

    def setUp(self):
        self.admin = User.objects.create_superuser(email='a2@example.com', password='x')
        self.client.force_login(self.admin)

    def test_warns_in_red_when_documents_go_to_local_disk(self):
        with override_settings(R2_PRIVATE_BUCKET=''):
            body = self.client.get('/admin/users/verificationdocument/').content.decode()
        self.assertIn('being lost', body)
        self.assertIn('R2_PRIVATE_BUCKET', body)

    def test_confirms_in_green_once_the_bucket_is_set(self):
        with override_settings(R2_PRIVATE_BUCKET='kavkazland-private'):
            body = self.client.get('/admin/users/verificationdocument/').content.decode()
        self.assertIn('stored safely', body)
        self.assertIn('kavkazland-private', body)
        self.assertNotIn('being lost', body)
