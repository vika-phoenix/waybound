"""
apps/payments/providers.py

Payment-method catalogue for the two rails.

The two rails settle to different bank accounts. Nothing here routes money —
each provider carries its own credentials, so the destination account follows
from which provider handled the charge. What this module does is decide *which
methods the checkout offers*, and record enough on the booking to reconcile
against each account afterwards.

A method is offered only when it is BOTH:
  * listed in settings.PAYMENT_METHODS_ENABLED, and
  * actually configured (its credentials are present).

That second condition matters: listing `stripe` without keys would render a
button that 500s on click. Turning the Russian rail back on is therefore an
env change (add `yookassa,sbp` to the list) with no code edit and no redeploy,
because the frontend renders whatever GET /payments/methods/ returns.
"""
from django.conf import settings

RAIL_RU = 'ru'
RAIL_INTL = 'intl'

# code -> catalogue entry. `currency` is what the provider actually charges in;
# amounts in another currency are converted at initiation (see views.convert_to_rub).
CATALOGUE = {
    'stripe': {
        'label': 'Card',
        'label_ru': 'Карта',
        'description': 'Visa, Mastercard, Amex, Apple Pay, Google Pay',
        'description_ru': 'Visa, Mastercard, Amex, Apple Pay, Google Pay',
        'rail': RAIL_INTL,
        'currency': 'USD',
        'icon': '💳',
    },
    'paypal': {
        'label': 'PayPal',
        'label_ru': 'PayPal',
        'description': 'Pay with a PayPal balance or a card as a guest',
        'description_ru': 'Оплата с баланса PayPal или картой без регистрации',
        'rail': RAIL_INTL,
        'currency': 'USD',
        'icon': '🅿️',
    },
    'yookassa': {
        'label': 'Card (Russia)',
        'label_ru': 'Банковская карта',
        'description': 'Russian-issued cards and Mir',
        'description_ru': 'Российские карты и Мир',
        'rail': RAIL_RU,
        'currency': 'RUB',
        'icon': '💳',
    },
    'sbp': {
        'label': 'SBP',
        'label_ru': 'СБП',
        'description': 'Russian instant bank transfer',
        'description_ru': 'Система быстрых платежей',
        'rail': RAIL_RU,
        'currency': 'RUB',
        'icon': '⚡',
    },
}


def is_configured(code):
    """True when the provider has the credentials it needs to actually charge."""
    if code in ('yookassa', 'sbp'):
        return bool(getattr(settings, 'YOOKASSA_SHOP_ID', '')
                    and getattr(settings, 'YOOKASSA_SECRET_KEY', ''))
    if code == 'stripe':
        return bool(getattr(settings, 'STRIPE_SECRET_KEY', ''))
    if code == 'paypal':
        return bool(getattr(settings, 'PAYPAL_CLIENT_ID', '')
                    and getattr(settings, 'PAYPAL_CLIENT_SECRET', ''))
    return False


def enabled_codes():
    """Method codes that are both switched on and usable, in catalogue order."""
    wanted = [c.strip().lower() for c in getattr(settings, 'PAYMENT_METHODS_ENABLED', [])]
    return [c for c in CATALOGUE if c in wanted and is_configured(c)]


def available_methods(lang='en'):
    """Catalogue entries for the enabled methods, shaped for the checkout UI."""
    out = []
    for code in enabled_codes():
        m = CATALOGUE[code]
        out.append({
            'code':        code,
            'label':       m['label_ru'] if lang == 'ru' else m['label'],
            'description': m['description_ru'] if lang == 'ru' else m['description'],
            'rail':        m['rail'],
            'currency':    m['currency'],
            'icon':        m['icon'],
        })
    return out


def rail_for(code):
    entry = CATALOGUE.get(code)
    return entry['rail'] if entry else None
