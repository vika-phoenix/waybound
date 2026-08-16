"""
The pages still described the booking flow we replaced.

Before instant book, a traveller paid and then waited for the guide to accept;
if nobody accepted within 48 hours the booking was cancelled and refunded. That
flow is gone — paying confirms the booking and takes the seat in the same
instant, and `booking_confirm` will not even accept a booking that is already
confirmed. But the sentences describing the old flow stayed on the help pages
in both languages and in the guide contract, so the site was telling travellers
to expect an approval that never comes and telling guides they had a decision
they no longer have.

Nothing catches stale prose except a test that reads it, so this reads it.
"""
import os
import re

from django.test import TestCase

from apps.bookings import cooling

FRONTEND = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'frontend'))


def read(name):
    with open(os.path.join(FRONTEND, name), encoding='utf-8') as fh:
        return fh.read()


def pages():
    return sorted(f for f in os.listdir(FRONTEND) if f.endswith('.html'))


class NoPageDescribesTheOldApprovalStepTest(TestCase):

    # Each is a claim that was true before instant book and is false now. They
    # are matched loosely on purpose: the wording moved between the English and
    # Russian versions, and it is the promise that must not come back, not a
    # particular sentence.
    GONE = [
        (r'48 hours?</strong> to confirm', 'the guide gets 48 h to accept'),
        (r"operator does(?:n't| not) confirm within 48", 'auto-cancel if not accepted'),
        (r'48 часов</strong> на подтверждение', 'the guide gets 48 h to accept (ru)'),
        (r'не подтвердит в течение 48', 'auto-cancel if not accepted (ru)'),
        (r'either confirm or decline the booking', 'confirm-or-decline (contract)'),
        (r'либо подтвердить, либо отклонить бронирование', 'confirm-or-decline (ru)'),
    ]

    def test_no_page_says_a_booking_waits_on_the_guide(self):
        for name in pages():
            text = read(name)
            for pattern, what in self.GONE:
                self.assertIsNone(
                    re.search(pattern, text),
                    f'{name} still promises: {what}')

    def test_the_help_pages_answer_the_question_the_other_way(self):
        """
        Deleting the FAQ would have been the smaller change and the worse one —
        travellers still ask whether someone has to approve their booking, and
        an unanswered question sends them to support.
        """
        self.assertIn('Does my guide have to confirm my booking?', read('help.html'))
        self.assertIn('Должен ли гид подтверждать моё бронирование?', read('help_ru.html'))


class TheChargeWordingFollowsTheSchemeTest(TestCase):
    """
    Two pages state when the card is charged, which is the half of the scheme
    that is not the window. They are marked regions now, so switching scheme
    rewrites them with everything else instead of leaving a contract page
    describing the other scheme's money.
    """

    MARKED = {
        'help.html':              ('charge', 'en'),
        'help_ru.html':           ('charge', 'ru'),
        'terms-experts.html':     ('charge_expert', 'en'),
        'terms-experts_ru.html':  ('charge_expert', 'ru'),
    }

    def test_each_page_carries_the_active_schemes_wording(self):
        for name, (key, lang) in self.MARKED.items():
            body = re.search(
                r'<!--cooling:%s-->(.*?)<!--/cooling-->' % key,
                read(name), re.DOTALL)
            self.assertIsNotNone(body, f'{name}: no cooling:{key} marker')
            self.assertEqual(body.group(1), cooling.text(lang)[key],
                             f'{name}: out of step — run tools/cooling_sync.py --write')


class TheTravellerIsToldTheGuideCanStillCancelTest(TestCase):
    """
    "Confirmed" reads as final, and it nearly is — but a guide can still cancel
    a confirmed booking right up to departure. That was stated only in the terms
    and on trust-safety, which is a defensible place to put it and not a place
    anyone reads. It belongs where the word "confirmed" appears.
    """

    def test_the_confirmation_page_says_it_in_both_languages(self):
        en = read('booking-confirmation.html')
        self.assertIn('guideCancelNote', en)
        self.assertIn('your guide has to cancel', en)
        self.assertIn('everything you paid', en)

        ru = read('booking-confirmation_ru.html')
        self.assertIn('guideCancelNote', ru)
        self.assertIn('придётся отменить', ru)
        self.assertIn('всё до копейки', ru)

    def test_it_also_says_who_to_ask_when_the_guide_goes_quiet(self):
        """
        Both pages promise contact within 24 hours and nothing measured it, so
        a traveller whose guide never wrote had no next step at all.
        """
        self.assertIn('contact.html', read('booking-confirmation.html'))
        self.assertIn('contact_ru.html', read('booking-confirmation_ru.html'))

    def test_the_promise_and_the_fallback_agree_on_when_to_worry(self):
        """
        The pages promised contact within 24 hours and the fallback offered to
        chase at 48, which left a day in which the promise was broken and the
        site said nothing. The outer bound has to be the same number in both
        places or one of them is wrong.
        """
        for name in ('booking.html', 'booking_ru.html',
                     'booking-confirmation.html', 'booking-confirmation_ru.html'):
            self.assertIn('48', read(name), f'{name}: no outer bound on guide contact')

    def test_the_guide_contract_states_what_cancelling_costs_them(self):
        for name, phrase in (('terms-experts.html', 'full refund of every amount paid'),
                             ('terms-experts_ru.html', 'возвращается вся уплаченная сумма')):
            self.assertIn(phrase, read(name), name)
