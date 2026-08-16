"""
The default cancellation policy is quoted on six pages, and paid by one.

Every page that can show a policy carries its own copy of the platform
default, for the case where a guide set none. They all said "full refund" at
30+ days while the backend kept 1% for the card fee — so the published terms
promised more than the code paid, which is the wrong way round to be wrong.

This reads the copies back out of the pages and holds them to the real table.
"""
import os
import re

from django.test import TestCase

from apps.bookings.views import PLATFORM_DEFAULT_CANCEL_POLICY

FRONTEND = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'frontend'))

# Every file with a hardcoded copy of the default tiers.
PAGES = [
    'tour_detail_page.html', 'tour_detail_page_ru.html',
    'booking.html', 'booking_ru.html',
    'booking-confirmation.html', 'booking-confirmation_ru.html',
]

TIER = re.compile(r'days_before_min:\s*(\d+),\s*days_before_max:\s*(null|\d+),'
                  r'\s*penalty_pct:\s*(\d+)')


class FrontendDefaultPolicyTest(TestCase):

    def _tiers(self, name):
        path = os.path.join(FRONTEND, name)
        with open(path, encoding='utf-8') as fh:
            return [(int(a), None if b == 'null' else int(b), int(p))
                    for a, b, p in TIER.findall(fh.read())]

    def test_every_page_quotes_the_policy_the_backend_applies(self):
        expected = {(t['days_before_min'], t['days_before_max'], t['penalty_pct'])
                    for t in PLATFORM_DEFAULT_CANCEL_POLICY}
        for name in PAGES:
            found = set(self._tiers(name))
            self.assertTrue(found, f'{name}: no default policy found — has it moved?')
            self.assertEqual(
                found, expected,
                f'{name} promises tiers the backend does not pay:\n'
                f'  page:    {sorted(found)}\n'
                f'  backend: {sorted(expected)}')

    def test_the_top_tier_is_not_described_as_a_full_refund(self):
        """
        The fee is small enough to look like a rounding error and be dropped
        from the copy, which is how it went unstated on eight pages.
        """
        top = min(PLATFORM_DEFAULT_CANCEL_POLICY,
                  key=lambda t: -(t['days_before_min']))
        if top['penalty_pct'] == 0:
            self.skipTest('Top tier really is a full refund')
        for name in ('terms.html', 'trust-safety.html'):
            with open(os.path.join(FRONTEND, name), encoding='utf-8') as fh:
                text = fh.read()
            self.assertNotIn('Full refund 30+ days', text, name)
            self.assertNotIn('before departure:</strong> Full refund.', text, name)
