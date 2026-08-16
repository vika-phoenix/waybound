"""
The catalogue has to hold together, because the failure is invisible.

A placeholder present in one language and missing from the other only crashes
when someone with that language triggers that message — so it would be a
Russian traveller, in the middle of a payment, and nobody else.
"""
import re

from django.core import mail as djmail
from django.test import TestCase

from apps.mail import lang_for, render, send
from apps.mail.messages import LANGS, MESSAGES, SHELL
from apps.users.models import User

PLACEHOLDER = re.compile(r'\{(\w+)\}')


def _keys():
    return [k for k in MESSAGES if not k.startswith('_')]


class CatalogueTest(TestCase):

    def test_every_message_exists_in_every_language(self):
        for key in _keys():
            for lang in LANGS:
                with self.subTest(key=key, lang=lang):
                    self.assertIn(lang, MESSAGES[key], f'{key} has no {lang}')

    def test_both_languages_take_the_same_placeholders(self):
        """
        The one that bites: a name in the English body and not the Russian one
        raises KeyError only for Russian readers, only for that message.
        """
        for key in _keys():
            sets = {}
            for lang in LANGS:
                text = MESSAGES[key][lang]
                found = set()
                for part in ('subject', 'body', 'cta'):
                    found |= set(PLACEHOLDER.findall(text.get(part, '')))
                sets[lang] = found
            self.assertEqual(sets['en'], sets['ru'],
                             f'{key}: placeholders differ — '
                             f'en-only {sets["en"] - sets["ru"]}, '
                             f'ru-only {sets["ru"] - sets["en"]}')

    def test_every_message_has_a_subject_and_a_body(self):
        for key in _keys():
            for lang in LANGS:
                text = MESSAGES[key][lang]
                self.assertTrue(text.get('subject', '').strip(), f'{key}/{lang}')
                self.assertTrue(text.get('body', '').strip(), f'{key}/{lang}')

    def test_the_shell_covers_every_language(self):
        for lang in LANGS:
            self.assertTrue(SHELL[lang]['footer'].strip())

    def test_russian_messages_are_actually_in_russian(self):
        """Catches an entry copied from English and never translated."""
        cyrillic = re.compile(r'[Ѐ-ӿ]')
        for key in _keys():
            body = MESSAGES[key]['ru']['body']
            with self.subTest(key=key):
                self.assertTrue(cyrillic.search(body), f'{key}: ru body has no Cyrillic')


class SendingTest(TestCase):

    def setUp(self):
        djmail.outbox = []

    def test_it_writes_in_the_readers_language(self):
        send('t@example.com', 'booking_confirmed', 'ru', url='https://x/',
             name='Нино', tour='Ушба', ref='VZ-1', departure='3 сентября')
        self.assertEqual(len(djmail.outbox), 1)
        self.assertIn('подтверждена', djmail.outbox[0].subject)

    def test_and_in_english_for_an_english_reader(self):
        send('t@example.com', 'booking_confirmed', 'en', url='https://x/',
             name='Nino', tour='Ushba', ref='VZ-1', departure='3 September')
        self.assertIn('confirmed', djmail.outbox[0].subject)

    def test_the_html_part_carries_the_same_words(self):
        send('t@example.com', 'capture_failed', 'ru', url='https://x/',
             name='Нино', tour='Ушба', ref='VZ-1', reason='Недостаточно средств',
             deadline='14:20')
        html = djmail.outbox[0].alternatives[0][0]
        self.assertIn('Недостаточно средств', html)
        self.assertIn('lang="ru"', html)
        self.assertIn('не отвечайте', html)

    def test_an_unknown_key_does_not_take_down_the_caller(self):
        """A notification failing must never fail the payment behind it."""
        self.assertFalse(send('t@example.com', 'no_such_message', 'en'))
        self.assertEqual(djmail.outbox, [])

    def test_a_missing_placeholder_is_logged_not_raised(self):
        self.assertFalse(send('t@example.com', 'booking_confirmed', 'en', name='X'))
        self.assertEqual(djmail.outbox, [])

    def test_no_recipient_is_a_quiet_no(self):
        self.assertFalse(send('', 'booking_confirmed', 'en'))


class MessageNotificationTest(TestCase):
    """
    Messages between a traveller and a guide.

    The old code built `email_body` and then rendered `tourist_body`, a name
    that only exists in other functions — so every send raised NameError into a
    bare except and nobody was ever notified. It failed silently for as long as
    it existed, which is why this is pinned.
    """

    def setUp(self):
        from datetime import date, timedelta
        from decimal import Decimal

        from apps.tours.models import Tour
        from apps.bookings.models import Booking

        djmail.outbox = []
        self.guide = User.objects.create_user(email='g@example.com', password='x',
                                              role=User.Role.OPERATOR)
        self.traveller = User.objects.create_user(
            email='t@example.com', password='x', language=User.Language.RU,
            first_name='Нино', last_name='Беридзе')
        tour = Tour.objects.create(operator=self.guide, title='Ушба', country='Georgia',
                                   destination='Mestia', price_adult=Decimal('500'),
                                   currency='USD', status=Tour.Status.LIVE, max_group=8)
        self.booking = Booking.objects.create(
            tour=tour, tourist=self.traveller, adults=1,
            departure_date=date.today() + timedelta(days=30),
            first_name='Нино', last_name='Беридзе', email='t@example.com',
            price_adult=Decimal('500'), total_price=Decimal('500'), currency='USD',
            status=Booking.Status.CONFIRMED)

    def _post(self, as_user, text):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(as_user)
        return c.post(f'/api/v1/bookings/{self.booking.pk}/message/',
                      {'message': text}, format='json')

    def test_a_guide_writing_reaches_the_traveller(self):
        res = self._post(self.guide, 'Встречаемся у подъёмника в 8 утра.')
        self.assertEqual(res.status_code, 200, getattr(res, 'data', None))
        self.assertEqual(len(djmail.outbox), 1)
        self.assertEqual(djmail.outbox[0].to, ['t@example.com'])
        self.assertIn('подъёмника', djmail.outbox[0].body)

    def test_and_in_the_travellers_language(self):
        self._post(self.guide, 'Привет')
        self.assertIn('Сообщение от гида', djmail.outbox[0].subject)

    def test_a_traveller_writing_reaches_the_guide(self):
        res = self._post(self.traveller, 'Do I need crampons?')
        self.assertEqual(res.status_code, 200, getattr(res, 'data', None))
        self.assertEqual(djmail.outbox[0].to, ['g@example.com'])
        self.assertIn('crampons', djmail.outbox[0].body)


class LanguageChoiceTest(TestCase):

    def test_it_uses_what_the_person_chose(self):
        u = User.objects.create_user(email='r@example.com', password='x',
                                     language=User.Language.RU)
        self.assertEqual(lang_for(u), 'ru')

    def test_english_when_nobody_chose(self):
        u = User.objects.create_user(email='e@example.com', password='x')
        self.assertEqual(lang_for(u), 'en')

    def test_english_when_there_is_no_account_at_all(self):
        """An offline booking has no user behind it, and a guess would be worse."""
        self.assertEqual(lang_for(None), 'en')
