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


class InternationalPayoutTest(TestCase):
    """
    The payout form was Russian-only: a 20-digit account and a 9-digit BIK.
    A guide in Georgia or Armenia — most of the target market — had no way to
    give details anyone could actually pay, and the payouts page called them
    "ready" as soon as a name was filled in.
    """

    def _guide(self, **kw):
        return User.objects.create_user(
            email=f'g{User.objects.count()}@example.com', password='x',
            role=User.Role.OPERATOR, **kw)

    def test_a_georgian_guide_can_be_paid(self):
        g = self._guide(payout_type='intl', payout_name='Nino T', payout_bank='Bank of Georgia',
                        payout_iban='GE29NB0000000101904917', payout_swift='BAGAGE22',
                        payout_bank_country='Georgia')
        self.assertTrue(g.payout_ready)
        self.assertIn('GE29NB0000000101904917', g.payout_summary)
        self.assertIn('BAGAGE22', g.payout_summary)
        self.assertNotIn('BIK', g.payout_summary, 'a BIK is meaningless for an IBAN transfer')

    def test_a_russian_guide_still_works(self):
        g = self._guide(payout_type='ru', payout_name='Ivan P', payout_bank='Sberbank',
                        payout_account='40817810099910004312', payout_bik='044525225')
        self.assertTrue(g.payout_ready)
        self.assertIn('044525225', g.payout_summary)
        self.assertNotIn('IBAN', g.payout_summary)

    def test_a_profile_from_before_the_choice_existed_is_read_as_russian(self):
        g = self._guide(payout_name='Old Guide', payout_bank='Tinkoff',
                        payout_account='40817810099910004312', payout_bik='044525225')
        self.assertEqual(g.payout_type, '')
        self.assertTrue(g.payout_ready, 'existing guides must not stop being payable')

    def test_half_filled_details_are_not_payable(self):
        """The old check passed on a name alone, which is not something you can pay."""
        self.assertFalse(self._guide(payout_name='Just A Name').payout_ready)
        self.assertFalse(self._guide(payout_type='intl', payout_name='N',
                                     payout_bank='B', payout_iban='GE29').payout_ready)
        self.assertFalse(self._guide(payout_type='ru', payout_name='N',
                                     payout_bank='B', payout_account='408').payout_ready)

    def test_stale_fields_from_the_other_form_do_not_count(self):
        """
        A guide who moved from a Russian account to an IBAN leaves BIK and
        account behind. Reading the columns rather than the chosen shape would
        call them payable while the IBAN is still blank.
        """
        g = self._guide(payout_type='intl', payout_name='Moved', payout_bank='B',
                        payout_account='40817810099910004312', payout_bik='044525225')
        self.assertFalse(g.payout_ready)


class ContactGatingTest(TestCase):
    """
    The guide used to see a traveller's email and phone from the moment a
    booking row existed — before any payment. The side with the incentive to
    take the trip off-platform got the contact details first, and for free.
    """

    def _booking(self, **kw):
        from datetime import date, timedelta
        from apps.tours.models import Tour
        guide = User.objects.create_user(
            email=f'cg{User.objects.count()}@example.com', password='x',
            role=User.Role.OPERATOR)
        tour = Tour.objects.create(
            operator=guide, title='T', country='Georgia', destination='K',
            price_adult=Decimal('300'), currency='USD',
            status=Tour.Status.LIVE, max_group=6)
        defaults = dict(
            tour=tour, adults=1, first_name='Nino', last_name='T',
            email='nino.tsereteli@example.com', phone='+995555123456',
            currency='USD', price_adult=Decimal('300'), total_price=Decimal('300'),
            departure_date=date.today() + timedelta(days=30),
            status=Booking.Status.PENDING, deposit_status='pending')
        defaults.update(kw)
        return Booking.objects.create(**defaults)

    def _serialized(self, bk):
        from apps.bookings.serializers import OperatorBookingSerializer
        return OperatorBookingSerializer(bk).data

    def test_an_unpaid_booking_hides_the_contact_details(self):
        d = self._serialized(self._booking())
        self.assertNotIn('nino.tsereteli', d['email'])
        self.assertNotIn('995555123456', d['phone'])
        self.assertFalse(d['contact_unlocked'])
        self.assertEqual(d['first_name'], 'Nino', 'the guide can still address them')

    def test_paying_the_deposit_reveals_them(self):
        d = self._serialized(self._booking(deposit_status='paid'))
        self.assertEqual(d['email'], 'nino.tsereteli@example.com')
        self.assertEqual(d['phone'], '+995555123456')
        self.assertTrue(d['contact_unlocked'])

    def test_a_confirmed_booking_reveals_them_even_if_paid_offline(self):
        d = self._serialized(self._booking(status=Booking.Status.CONFIRMED))
        self.assertTrue(d['contact_unlocked'])

    def test_a_masked_value_is_never_the_real_one(self):
        """A partial mask that leaks the domain would defeat the point."""
        d = self._serialized(self._booking())
        self.assertNotIn('example.com', d['email'])


class ContactDetectionTest(TestCase):
    """
    Messages are flagged, never rewritten.

    The filter can misread a long permit number or a price written with spaces,
    and rewriting changed the text without telling the sender. Detection makes
    the rule visible and gives an audit trail without ever being able to damage
    a message.
    """

    def _enquiry(self, message):
        from apps.tours.models import Tour
        from apps.bookings.models import EnquiryMessage
        guide = User.objects.create_user(
            email=f'ms{User.objects.count()}@example.com', password='x',
            role=User.Role.OPERATOR)
        tour = Tour.objects.create(
            operator=guide, title='T', country='Georgia', destination='K',
            price_adult=Decimal('300'), status=Tour.Status.LIVE, max_group=6)
        return EnquiryMessage.objects.create(
            tour=tour, name='Nino', email='nino@example.com', message=message)

    def test_the_message_is_never_altered(self):
        text = 'Call me on +995 555 123 456'
        e = self._enquiry(text)
        e.refresh_from_db()
        self.assertEqual(e.message, text, 'the sender wrote this; it stays as written')

    def test_a_phone_number_is_flagged(self):
        self.assertTrue(self._enquiry('Call me on +995 555 123 456').has_contact_details)

    def test_an_email_is_flagged(self):
        self.assertTrue(self._enquiry('write to nino.t@gmail.com').has_contact_details)

    def test_a_telegram_handle_is_flagged(self):
        self.assertTrue(self._enquiry('my telegram is @ninoguide').has_contact_details)

    def test_ordinary_trip_detail_is_not_flagged(self):
        self.assertFalse(self._enquiry(
            'We start at 07:30 and climb to 2400m. Price is 1,250 USD.').has_contact_details)

    def test_the_enquirer_email_is_masked_until_they_book(self):
        from apps.bookings.serializers import EnquiryDetailSerializer
        e = self._enquiry('Hello, are dates in June possible?')
        data = EnquiryDetailSerializer(e).data
        self.assertNotIn('example.com', data['email'])
        self.assertEqual(data['name'], 'Nino', 'the guide can still address them')
