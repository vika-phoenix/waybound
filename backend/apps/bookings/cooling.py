"""
apps/bookings/cooling.py
The one place the free-cancellation window is defined.

It used to live in three kinds of place at once: the arithmetic in
booking_create, the contractual wording in terms.html and terms-experts.html,
and the explanatory copy on six other pages in two languages. Widening it from
30 minutes to 24 hours meant editing all of them, and the pages that were
missed carried a promise the code no longer kept.

So the bands and the words describing them are the same object now. Switching
scheme is a settings change; nothing else has to be edited, and nothing can
drift out of step because there is only one copy.

  COOLING_OFF_SCHEME = 'tiered'   the window scales with how resellable the
                                  seat is: 24 h a month out, 2 h inside a
                                  month, 30 min inside a week
  COOLING_OFF_SCHEME = 'flat'     one window for everyone, 30 minutes

Adding a third is data, not code: a bands list and its four strings per
language.
"""
from django.conf import settings

# The one default. settings.py reads the env var and leaves it empty when
# unset, so this stays the single answer to "which scheme is running" — for
# the app and for tools/cooling_sync.py, which cannot import Django settings.
DEFAULT_SCHEME = 'flat'

# Bands are matched top to bottom on days-until-departure, so the first whose
# min_days is met wins. The last must be min_days 0 or a near booking matches
# nothing.
SCHEMES = {
    'tiered': {
        # The window is long enough that charging up front and refunding would
        # cost us the processor fee on every change of mind, so the card is
        # authorised at booking and charged only once the window shuts. A
        # cancellation before that is a dropped authorisation: free to everyone.
        'defers_capture': True,
        'bands': [
            {'min_days': 31, 'minutes': 24 * 60},
            {'min_days': 8,  'minutes': 120},
            {'min_days': 0,  'minutes': 30},
        ],
        'text': {
            'en': {
                'headline': '24 hours to change your mind.',
                'sentence': ('If your departure is more than 30 days away, you may cancel '
                             'within 24 hours of booking for a full refund. Between 8 and '
                             '30 days the window is 2 hours, and 7 days or less it is 30 '
                             'minutes — a seat close to departure is harder to resell, so '
                             'it is held open for less time.'),
                'detail': ('That window is 2 hours if your departure is under a month '
                           'away, and 30 minutes inside the last week.'),
                # Brackets belong to the value: it is always dropped mid-sentence.
                'parenthetical': ('(24 h if departure is more than 30 days away; '
                                  '2 h if 8–30 days; 30 min if 7 days or less)'),
                'rows': [
                    ('Departure more than 30 days away', '24 hours'),
                    ('Departure 8–30 days away', '2 hours'),
                    ('Departure 7 days or less away', '30 minutes'),
                ],
            },
            'ru': {
                'headline': '24 часа на раздумья.',
                'sentence': ('Если до отправления больше 30 дней, вы можете отменить в '
                             'течение 24 часов после бронирования с полным возвратом. '
                             'При 8–30 днях период составляет 2 часа, а при 7 днях или '
                             'меньше — 30 минут: место близко к дате сложнее перепродать, '
                             'поэтому оно держится открытым меньше.'),
                'detail': ('Если до отправления меньше месяца — 2 часа, '
                           'в последнюю неделю — 30 минут.'),
                'parenthetical': ('(24 ч, если до отправления больше 30 дней; '
                                  '2 ч при 8–30 днях; 30 мин, если 7 дней или меньше)'),
                'rows': [
                    ('До отправления больше 30 дней', '24 часа'),
                    ('До отправления 8–30 дней', '2 часа'),
                    ('До отправления 7 дней или меньше', '30 минут'),
                ],
            },
        },
    },
    'flat': {
        # Half an hour is short enough that few people use it, so the simpler
        # machine wins: charge at booking like any shop, refund in full if they
        # cancel inside the window, and absorb the processor fee on the few who
        # do. No authorisations outstanding, no capture to schedule, nothing to
        # fail a day later.
        'defers_capture': False,
        'bands': [
            {'min_days': 0, 'minutes': 30},
        ],
        'text': {
            'en': {
                'headline': '30 minutes to change your mind.',
                'sentence': ('You may cancel within 30 minutes of booking for a full '
                             'refund, whatever your departure date.'),
                # One band, so there is nothing further to qualify. Under the
                # tiered scheme this carries the other two figures; here it
                # would only say thirty minutes a second time on the same page.
                'detail': '',
                'parenthetical': '(30 minutes from booking)',
                'rows': [
                    ('Every booking, whenever you travel', '30 minutes'),
                ],
            },
            'ru': {
                'headline': '30 минут на раздумья.',
                'sentence': ('Вы можете отменить в течение 30 минут после бронирования '
                             'с полным возвратом, независимо от даты отправления.'),
                'detail': '',
                'parenthetical': '(30 минут с момента бронирования)',
                'rows': [
                    ('Любое бронирование, в любую дату', '30 минут'),
                ],
            },
        },
    },
}


def active_scheme_name():
    name = getattr(settings, 'COOLING_OFF_SCHEME', '') or DEFAULT_SCHEME
    return name if name in SCHEMES else DEFAULT_SCHEME


def active_scheme():
    return SCHEMES[active_scheme_name()]


def defers_capture():
    """
    Whether the active scheme holds the card and charges later, or charges at
    booking like any shop.

    It belongs to the scheme rather than a flag of its own because the two are
    one decision: a long window makes charge-then-refund expensive, and a short
    one makes deferring more machinery than it saves. Splitting them into two
    settings would let someone pick the pair that has the costs of both.
    """
    return bool(active_scheme().get('defers_capture'))


def window_minutes(days_to_departure):
    """
    How long this booking gets, in minutes.

    A booking with no departure date is treated as far out — it is the
    generous reading, and the only bookings without one are ours.
    """
    bands = active_scheme()['bands']
    if days_to_departure is None:
        return bands[0]['minutes']
    for band in bands:
        if days_to_departure >= band['min_days']:
            return band['minutes']
    return bands[-1]['minutes']


def text(lang='en'):
    """The wording for the active scheme, for the API and the pages."""
    strings = active_scheme()['text']
    return strings.get(lang, strings['en'])


def as_payload():
    """Everything a page needs to describe the window, in both languages."""
    scheme = active_scheme()
    return {
        'scheme': active_scheme_name(),
        'bands': scheme['bands'],
        'text': {lang: dict(vals) for lang, vals in scheme['text'].items()},
    }
