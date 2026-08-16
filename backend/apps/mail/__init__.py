"""
apps/mail — one way to send an email, in the reader's own language.

Every message the platform sends lives in messages.py, in English and Russian,
as text with named placeholders. Nothing here composes wording; this module
only picks the language, fills the placeholders, wraps the result in the shell
and sends it.

    from apps.mail import send
    send(booking.email, 'booking_confirmed', lang_for(booking.tourist),
         name='Nino', tour='Ushba', ref='VZ-1234', url=f'{site}/my-bookings.html')

Why one language and not both in one email: a bilingual message is twice as
long, and the line that matters — a deadline, an amount, what to press — ends
up halfway down, competing with the same sentence in a language the reader is
skipping. Sending the one they chose is shorter and clearer, and we already
know which one they chose, because they picked a site to read.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from .messages import MESSAGES, ROWS, SHELL

logger = logging.getLogger(__name__)

DEFAULT_LANG = 'en'


def lang_for(user, fallback=DEFAULT_LANG):
    """
    Which language to write to this person in.

    Falls back rather than guessing: an offline booking has no account behind
    it, and a guess from a name or a country would be wrong often enough to
    matter.
    """
    lang = getattr(user, 'language', None) if user is not None else None
    return lang if lang in MESSAGES.get('_langs', ('en', 'ru')) else fallback


def render(key, lang, **vars):
    """The subject and body for one message. Raises if the key is unknown."""
    entry = MESSAGES[key]
    text = entry.get(lang) or entry[DEFAULT_LANG]
    subject = text['subject'].format(**vars)
    body = text['body'].format(**vars)
    cta = text.get('cta', '').format(**vars) if text.get('cta') else ''
    return subject, body, cta


def booking_rows(booking, lang=DEFAULT_LANG):
    """
    The detail table that rides along with the booking emails.

    Built here rather than in the catalogue because the values come from the
    booking; only the labels are wording, and those live in messages.ROWS.
    """
    L = ROWS.get(lang) or ROWS[DEFAULT_LANG]

    def plural(n, one, many):
        return f'{n} {one if n == 1 else many}'

    pax = [plural(booking.adults, L['adult'], L['adults'])]
    if booking.children:
        pax.append(plural(booking.children, L['child'], L['children']))
    if booking.infants:
        pax.append(plural(booking.infants, L['infant'], L['infants']))

    rows = [
        (L['ref'],        booking.reference),
        (L['tour'],       booking.tour.title),
        (L['departure'],  str(booking.departure_date) if booking.departure_date else L['tbc']),
        (L['travellers'], ', '.join(pax)),
        (L['total'],      f'{booking.currency} {booking.total_price:,.0f}'),
    ]
    html = '<table style="width:100%;border-collapse:collapse;margin-bottom:16px;font-size:13px">'
    for i, (label, val) in enumerate(rows):
        bg = '#f4f8fb' if i % 2 == 0 else '#ffffff'
        html += (f'<tr style="background:{bg}"><td style="padding:8px 12px;font-weight:700;'
                 f'color:#607080;width:40%">{label}</td>'
                 f'<td style="padding:8px 12px;color:#0d1f2d">{val}</td></tr>')
    return html + '</table>', '\n'.join(f'{k}: {v}' for k, v in rows)


def _html(lang, title, body, cta_label, cta_url, extra_html=''):
    """The branded shell. Only the footer and the language tag differ."""
    shell = SHELL.get(lang) or SHELL[DEFAULT_LANG]
    paragraphs = ''.join(
        '<p style="margin:0 0 14px;font-size:14.5px;color:#33414d;line-height:1.75">%s</p>'
        % line.replace('\n', '<br>')
        for line in body.split('\n\n') if line.strip()
    )
    button = ''
    if cta_label and cta_url:
        button = (
            '<tr><td style="padding:4px 32px 36px;text-align:center">'
            '<a href="%s" style="display:inline-block;background:#4fa8d4;color:#0d1f2d;'
            'text-decoration:none;font-weight:700;font-size:15px;padding:14px 36px;'
            'border-radius:8px;font-family:\'Helvetica Neue\',Arial,sans-serif">%s &rarr;</a>'
            '</td></tr>' % (cta_url, cta_label)
        )
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f5f9;font-family:'Helvetica Neue',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f5f9;padding:40px 16px">
    <tr><td>
      <table width="600" cellpadding="0" cellspacing="0" align="center"
             style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;
                    overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,.10)">
        <tr><td style="background:#1a2535;padding:22px 32px">
          <span style="font-family:Georgia,serif;font-size:22px;color:#4fa8d4;font-weight:400;letter-spacing:.03em">kavkazland</span>
        </td></tr>
        <tr><td style="padding:32px 32px 20px">
          <h2 style="margin:0 0 16px;font-size:20px;color:#0d1f2d;font-weight:700;line-height:1.3">{title}</h2>
          {paragraphs}
          {extra_html}
        </td></tr>
        {button}
        <tr><td style="background:#f4f8fb;padding:18px 32px;border-top:1px solid #e0eaf0">
          <p style="margin:0;font-size:12px;color:#8a9aaa;line-height:1.65">{shell['footer']}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def send(to, key, lang=DEFAULT_LANG, url=None, booking=None, **vars):
    """
    Send one catalogued message. Never raises: a failed notification must not
    take down the booking, payment or cancellation that triggered it.

    Pass `booking` to append the detail table — reference, tour, departure,
    travellers, total — under the message, in the same language.
    """
    if not to:
        return False
    try:
        subject, body, cta = render(key, lang, **vars)
    except KeyError as exc:
        # A missing key or placeholder is our bug, not the sender's problem.
        logger.error('Email %r could not be built: missing %s', key, exc)
        return False

    # The table goes into the plain text as lines and into the HTML as a table.
    # Appending it to `body` before rendering the HTML would put it in twice.
    rows_html, rows_text = ('', '')
    plain = body
    if booking is not None:
        rows_html, rows_text = booking_rows(booking, lang)
        plain = f'{body}\n\n{rows_text}'

    from_em = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@kavkazland.com')
    try:
        msg = EmailMultiAlternatives(subject, plain, from_em, [to])
        msg.attach_alternative(_html(lang, subject, body, cta, url, rows_html), 'text/html')
        msg.send(fail_silently=True)
        logger.info('Sent %r to %s in %s', key, to, lang)
        return True
    except Exception as exc:
        logger.error('Email %r to %s failed: %s', key, to, exc)
        return False
