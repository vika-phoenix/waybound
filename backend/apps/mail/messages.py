# -*- coding: utf-8 -*-
"""
apps/mail/messages.py — every email the platform sends, in both languages.

THIS IS THE FILE TO EDIT WHEN YOU WANT TO CHANGE WHAT AN EMAIL SAYS.
Nothing else composes wording. Change the text here and it changes everywhere
that message is sent.

Each entry looks like:

    'some_key': {
        'en': {'subject': ..., 'body': ..., 'cta': ...},
        'ru': {'subject': ..., 'body': ..., 'cta': ...},
    }

  subject   the line in their inbox
  body      the message. A blank line starts a new paragraph. Plain text is
            sent as-is and also wrapped in the branded shell as HTML, so the
            same words reach someone whose client blocks HTML.
  cta       the label on the button. The button's link is passed in as `url`
            at the call site, because it depends on the booking.

Placeholders are named, in {braces}, and are filled at the call site. Both
languages must use the same set — a placeholder in one and not the other is a
crash when that language is chosen, so there is a test that compares them.

Rules of thumb for the text itself:
  - Say the thing that has to happen, and by when, in the first line.
  - Amounts, dates and deadlines belong in the body, not only the button.
  - No exclamation marks in anything about money.
  - Russian is not a translation of the English word for word; it is the same
    message written for a Russian reader.
"""

# Languages this catalogue covers. lang_for() falls back to English for
# anything else, including an offline booking with no account behind it.
LANGS = ('en', 'ru')

# The wrapper around every message. Only these differ by language; the layout
# and branding are shared.
SHELL = {
    'en': {
        'footer': ('This is an automated notification from Kavkazland. '
                   '<strong style="color:#607080">Please do not reply to this email</strong> — '
                   'replies are not monitored. Use the button above to continue on Kavkazland.'),
    },
    'ru': {
        'footer': ('Это автоматическое уведомление от Kavkazland. '
                   '<strong style="color:#607080">Пожалуйста, не отвечайте на это письмо</strong> — '
                   'ответы не читаются. Продолжить можно по кнопке выше.'),
    },
}


# Why a booking was cancelled and what happens to the money. One sentence,
# dropped into booking_cancelled as {refund_line}, so there is a single
# cancellation email rather than four near-identical ones.
CANCEL_REASONS = {
    'en': {
        'tourist': 'The cancellation was made from your account. Any refund due under '
                   'the tour\'s cancellation policy is on its way to your original '
                   'payment method, and takes 3–10 business days to appear.',
        'operator': 'Your guide cancelled it. That is their decision, not yours, so you '
                    'are refunded in full — everything you paid, whatever the '
                    'cancellation policy says. It takes 3–10 business days to appear.',
        'operator_timeout': 'Your guide did not confirm it in time, so it was cancelled '
                            'automatically. You are refunded in full, and it takes '
                            '3–10 business days to appear.',
        'system_past_departure': 'The departure date passed without the booking being '
                                 'confirmed, so it was cancelled automatically. You are '
                                 'refunded in full, and it takes 3–10 business days to '
                                 'appear. We are sorry — this should not have happened.',
    },
    'ru': {
        'tourist': 'Отмена сделана из вашего аккаунта. Возврат, положенный по условиям '
                   'отмены тура, уже отправлен на ту же карту и появится в течение '
                   '3–10 рабочих дней.',
        'operator': 'Бронь отменил гид. Это его решение, а не ваше, поэтому вам '
                    'возвращается всё, что вы оплатили, независимо от условий отмены. '
                    'Деньги придут в течение 3–10 рабочих дней.',
        'operator_timeout': 'Гид не подтвердил бронь вовремя, поэтому она отменена '
                            'автоматически. Вам возвращается полная сумма, деньги '
                            'придут в течение 3–10 рабочих дней.',
        'system_past_departure': 'Дата отправления прошла, а бронь так и не была '
                                 'подтверждена, поэтому она отменена автоматически. '
                                 'Вам возвращается полная сумма в течение 3–10 рабочих '
                                 'дней. Извините — так быть не должно было.',
    },
}


# Labels for the detail table that rides along with the booking emails. Same
# rows, same order, so a Russian reader and an English one see the same shape.
ROWS = {
    'en': {'ref': 'Booking ref', 'tour': 'Tour', 'departure': 'Departure',
           'travellers': 'Travellers', 'total': 'Total', 'tbc': 'To be confirmed',
           'adult': 'adult', 'adults': 'adults', 'child': 'child',
           'children': 'children', 'infant': 'infant', 'infants': 'infants'},
    'ru': {'ref': 'Номер брони', 'tour': 'Тур', 'departure': 'Отправление',
           'travellers': 'Путешественники', 'total': 'Итого',
           'tbc': 'Уточняется',
           'adult': 'взрослый', 'adults': 'взрослых', 'child': 'ребёнок',
           'children': 'детей', 'infant': 'младенец', 'infants': 'младенцев'},
}


MESSAGES = {
    '_langs': LANGS,

    # ── Booking made, not yet paid ──────────────────────────────────────────
    'booking_created': {
        'en': {
            'subject': 'Booking received: {tour} — complete your payment',
            'body': ('Hi {name},\n\n'
                     'We have your booking for "{tour}".\n\n'
                     'Your place is not held until the deposit is paid. If we do not '
                     'receive it within 24 hours, the booking is cancelled and the '
                     'seat goes back on sale.'),
            'cta': 'Complete payment',
        },
        'ru': {
            'subject': 'Бронирование получено: {tour} — завершите оплату',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Мы получили вашу бронь на «{tour}».\n\n'
                     'Место закрепляется только после оплаты депозита. Если он не '
                     'поступит в течение 24 часов, бронь будет отменена, а место '
                     'вернётся в продажу.'),
            'cta': 'Оплатить',
        },
    },

    # ── Paid and confirmed ──────────────────────────────────────────────────
    'booking_confirmed': {
        'en': {
            # The detail table below carries the reference, departure and
            # total, so the body does not repeat them.
            'subject': 'Booking confirmed: {tour}',
            'body': ('Hi {name},\n\n'
                     'Your place on "{tour}" is confirmed and your deposit has been '
                     'received.\n\n'
                     'Your guide has been told and can now message you here.'),
            'cta': 'View my booking',
        },
        'ru': {
            'subject': 'Бронь подтверждена: {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Ваше место на «{tour}» подтверждено, депозит получен.\n\n'
                     'Гид уже знает о брони и может написать вам здесь.'),
            'cta': 'Открыть бронь',
        },
    },

    # ── Deposit reminder ────────────────────────────────────────────────────
    'deposit_reminder': {
        'en': {
            'subject': '{label}: complete your booking for {tour}',
            'body': ('Hi {name},\n\n'
                     'Your booking for "{tour}" is still waiting for the deposit.\n'
                     'Reference: {ref}\n\n'
                     'The place is released in about {hours_left} hour(s) if payment '
                     'does not arrive.'),
            'cta': 'Pay now',
        },
        'ru': {
            'subject': '{label}: завершите бронирование «{tour}»',
            'body': ('Здравствуйте, {name}!\n\n'
                     'По брони на «{tour}» всё ещё не внесён депозит.\n'
                     'Номер брони: {ref}\n\n'
                     'Место освободится примерно через {hours_left} ч., если оплата '
                     'не поступит.'),
            'cta': 'Оплатить',
        },
    },

    # ── Balance reminder ────────────────────────────────────────────────────
    'balance_reminder': {
        'en': {
            'subject': 'Balance due in {label}: {tour}',
            'body': ('Hi {name},\n\n'
                     'The remaining balance for "{tour}" is due on {due_date}.\n'
                     'Reference: {ref}\n'
                     'Amount outstanding: {amount}'),
            'cta': 'Pay balance',
        },
        'ru': {
            'subject': 'Остаток к оплате через {label}: {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Остаток по туру «{tour}» нужно оплатить до {due_date}.\n'
                     'Номер брони: {ref}\n'
                     'Сумма к оплате: {amount}'),
            'cta': 'Оплатить остаток',
        },
    },

    # ── Cancelled ───────────────────────────────────────────────────────────
    'booking_cancelled': {
        'en': {
            'subject': 'Booking cancelled: {tour}',
            'body': ('Hi {name},\n\n'
                     'Your booking for "{tour}" has been cancelled.\n'
                     'Reference: {ref}\n\n'
                     '{refund_line}'),
            'cta': 'View my bookings',
        },
        'ru': {
            'subject': 'Бронь отменена: {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Ваша бронь на «{tour}» отменена.\n'
                     'Номер брони: {ref}\n\n'
                     '{refund_line}'),
            'cta': 'Мои брони',
        },
    },

    # ── The card did not go through when we charged it ──────────────────────
    # Only reachable while the scheme holds cards rather than charging them.
    # Time-limited and money is at stake, so this is the worst one to send in
    # a language the reader does not use.
    'capture_failed': {
        'en': {
            'subject': 'We could not charge your card for {tour}',
            'body': ('Hi {name},\n\n'
                     'Your place on "{tour}" is still held, but the payment did not go '
                     'through when we tried to charge your card.\n'
                     'Reference: {ref}\n\n'
                     '{reason}\n\n'
                     'Please pay by {deadline} to keep your place — a different card is '
                     'fine. After that the seat goes back on sale.'),
            'cta': 'Pay now',
        },
        'ru': {
            'subject': 'Не удалось списать оплату по карте — {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Ваше место на «{tour}» пока сохраняется, но списание с карты не '
                     'прошло.\n'
                     'Номер брони: {ref}\n\n'
                     '{reason}\n\n'
                     'Оплатите до {deadline}, чтобы сохранить место — можно другой '
                     'картой. После этого место вернётся в продажу.'),
            'cta': 'Оплатить',
        },
    },
    'capture_reminder': {
        'en': {
            'subject': 'Reminder: your card still needs attention for {tour}',
            'body': ('Hi {name},\n\n'
                     'We still could not take payment for "{tour}".\n'
                     'Reference: {ref}\n\n'
                     '{reason}\n\n'
                     'Your place is released after {deadline} unless the payment goes '
                     'through. A different card is fine.'),
            'cta': 'Pay now',
        },
        'ru': {
            'subject': 'Напоминание: оплата по карте не прошла — {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Списание по брони на «{tour}» так и не прошло.\n'
                     'Номер брони: {ref}\n\n'
                     '{reason}\n\n'
                     'Место освободится после {deadline}, если оплата не пройдёт. '
                     'Можно оплатить другой картой.'),
            'cta': 'Оплатить',
        },
    },

    # ── Account ─────────────────────────────────────────────────────────────
    'password_reset': {
        'en': {
            'subject': 'Reset your Kavkazland password',
            'body': ('Hi {name},\n\n'
                     'Use the button below to set a new password. The link works for '
                     '{valid_for} and only once.\n\n'
                     'If you did not ask for this, you can ignore this email — nothing '
                     'has changed on your account.'),
            'cta': 'Set a new password',
        },
        'ru': {
            'subject': 'Восстановление пароля Kavkazland',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Нажмите кнопку ниже, чтобы задать новый пароль. Ссылка '
                     'действует {valid_for} и только один раз.\n\n'
                     'Если вы не запрашивали смену пароля, просто проигнорируйте это '
                     'письмо — с аккаунтом ничего не произошло.'),
            'cta': 'Задать новый пароль',
        },
    },

    # ── To the guide ────────────────────────────────────────────────────────
    'operator_new_booking': {
        'en': {
            'subject': 'New booking: {tour}',
            'body': ('{name} has booked "{tour}".\n\n'
                     'Reference: {ref}\n'
                     'Departure: {departure}\n'
                     'Travellers: {guests}\n\n'
                     'The place is already confirmed and the seat is off your '
                     'departure — nothing to approve.'),
            'cta': 'Open booking',
        },
        'ru': {
            'subject': 'Новая бронь: {tour}',
            'body': ('{name} забронировал(а) «{tour}».\n\n'
                     'Номер брони: {ref}\n'
                     'Дата отправления: {departure}\n'
                     'Путешественников: {guests}\n\n'
                     'Бронь уже подтверждена, место списано с даты — подтверждать '
                     'ничего не нужно.'),
            'cta': 'Открыть бронь',
        },
    },
    'operator_message': {
        'en': {
            'subject': 'Message from your guide — {tour}',
            'body': ('Hi {name},\n\n'
                     'Your guide has written to you about "{tour}".\n\n'
                     '{message}'),
            'cta': 'Reply',
        },
        'ru': {
            'subject': 'Сообщение от гида — {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Ваш гид написал вам по туру «{tour}».\n\n'
                     '{message}'),
            'cta': 'Ответить',
        },
    },
}
