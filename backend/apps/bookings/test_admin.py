"""Prove the payout admin is reachable and renders, not just that it imports."""
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
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
