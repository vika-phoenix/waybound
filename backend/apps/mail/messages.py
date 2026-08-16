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

    # ── Enquiries, before there is a booking ────────────────────────────────
    'enquiry_received': {
        'en': {
            'subject': 'We passed your question on — {tour}',
            'body': ('Hi {name},\n\n'
                     'Your question about "{tour}" has gone to the guide, who usually '
                     'replies within a day.\n\n'
                     'You asked:\n{message}'),
            'cta': 'View the tour',
        },
        'ru': {
            'subject': 'Мы передали ваш вопрос — {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Ваш вопрос о туре «{tour}» отправлен гиду — обычно он отвечает '
                     'в течение суток.\n\n'
                     'Ваш вопрос:\n{message}'),
            'cta': 'Открыть тур',
        },
    },
    'enquiry_reply': {
        'en': {
            'subject': 'Your guide replied — {tour}',
            'body': ('Hi {name},\n\n'
                     'The guide for "{tour}" has answered you.\n\n'
                     '{message}'),
            'cta': 'Reply',
        },
        'ru': {
            'subject': 'Гид ответил — {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Гид тура «{tour}» ответил на ваш вопрос.\n\n'
                     '{message}'),
            'cta': 'Ответить',
        },
    },

    # ── Waitlist ────────────────────────────────────────────────────────────
    'waitlist_joined': {
        'en': {
            'subject': 'You are on the waitlist — {tour}',
            'body': ('Hi {name},\n\n'
                     'You are on the waitlist for "{tour}" on {departure}.\n\n'
                     'If a place opens up we will email you. Nothing is booked and '
                     'nothing has been charged.'),
            'cta': 'View the tour',
        },
        'ru': {
            'subject': 'Вы в списке ожидания — {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Вы в списке ожидания на тур «{tour}» {departure}.\n\n'
                     'Если место освободится, мы напишем. Бронь не создана и деньги '
                     'не списаны.'),
            'cta': 'Открыть тур',
        },
    },
    'waitlist_spot_open': {
        'en': {
            'subject': 'A place opened up — {tour}',
            'body': ('Hi {name},\n\n'
                     'A place has opened on "{tour}" for {departure}.\n\n'
                     'Places are not held for the waitlist, so this is first come, '
                     'first served.'),
            'cta': 'Book it',
        },
        'ru': {
            'subject': 'Освободилось место — {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'На туре «{tour}» освободилось место на {departure}.\n\n'
                     'Места по списку ожидания не резервируются — кто успел, тот и '
                     'занял.'),
            'cta': 'Забронировать',
        },
    },

    # ── The tour changed under a booking ────────────────────────────────────
    'tour_changed': {
        'en': {
            'subject': 'Something changed on your booking — {tour}',
            'body': ('Hi {name},\n\n'
                     'The guide has changed something about "{tour}" since you booked.\n\n'
                     '{changes}\n\n'
                     'If this does not work for you, you can cancel free of charge until '
                     '{deadline} — whatever the usual cancellation policy says.'),
            'cta': 'View my booking',
        },
        'ru': {
            'subject': 'В вашей брони кое-что изменилось — {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Гид изменил условия тура «{tour}» после вашего бронирования.\n\n'
                     '{changes}\n\n'
                     'Если это вам не подходит, вы можете отменить бронь бесплатно до '
                     '{deadline} — независимо от обычных условий отмены.'),
            'cta': 'Открыть бронь',
        },
    },

    # ── After the trip ──────────────────────────────────────────────────────
    'review_reminder': {
        'en': {
            'subject': 'How was {tour}?',
            'body': ('Hi {name},\n\n'
                     'You travelled with us on "{tour}". If you have a few minutes, a '
                     'review helps the next person decide — and it helps your guide '
                     'more than anything else we can offer them.'),
            'cta': 'Write a review',
        },
        'ru': {
            'subject': 'Как прошёл тур «{tour}»?',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Вы были с нами на туре «{tour}». Если найдётся пара минут, отзыв '
                     'поможет следующему путешественнику решиться — и вашему гиду это '
                     'полезнее всего остального, что мы можем ему дать.'),
            'cta': 'Оставить отзыв',
        },
    },

    # ── The guide called off a departure ────────────────────────────────────
    'departure_cancelled': {
        'en': {
            'subject': 'Your departure was cancelled — {tour}',
            'body': ('Hi {name},\n\n'
                     'The {departure} departure of "{tour}" has been called off by the '
                     'guide.\n\n'
                     'This was not your decision, so you are refunded in full — '
                     'everything you paid, whatever the cancellation policy says. It '
                     'takes 3–10 business days to appear.'),
            'cta': 'Find another tour',
        },
        'ru': {
            'subject': 'Отправление отменено — {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Отправление тура «{tour}» {departure} отменено гидом.\n\n'
                     'Это не ваше решение, поэтому вам возвращается вся оплаченная '
                     'сумма, независимо от условий отмены. Деньги придут в течение '
                     '3–10 рабочих дней.'),
            'cta': 'Выбрать другой тур',
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
    'traveller_message': {
        'en': {
            'subject': 'Message from a traveller — {ref}',
            'body': ('{name} has written to you about "{tour}".\n\n'
                     '{message}'),
            'cta': 'Reply',
        },
        'ru': {
            'subject': 'Сообщение от путешественника — {ref}',
            'body': ('{name} написал(а) вам по туру «{tour}».\n\n'
                     '{message}'),
            'cta': 'Ответить',
        },
    },
    'operator_new_enquiry': {
        'en': {
            'subject': 'A question about {tour}',
            'body': ('{name} has asked about "{tour}".\n\n'
                     '{message}\n\n'
                     'Enquiries that get an answer the same day convert best.'),
            'cta': 'Reply',
        },
        'ru': {
            'subject': 'Вопрос по туру «{tour}»',
            'body': ('{name} спрашивает о туре «{tour}».\n\n'
                     '{message}\n\n'
                     'Быстрый ответ в тот же день заметно повышает шанс брони.'),
            'cta': 'Ответить',
        },
    },
    'operator_enquiry_reply': {
        'en': {
            'subject': 'A traveller replied — {tour}',
            'body': ('{name} has replied about "{tour}".\n\n{message}'),
            'cta': 'Reply',
        },
        'ru': {
            'subject': 'Путешественник ответил — {tour}',
            'body': ('{name} ответил(а) по туру «{tour}».\n\n{message}'),
            'cta': 'Ответить',
        },
    },
    'operator_waitlist_entry': {
        'en': {
            'subject': 'Someone is waiting for a place — {tour}',
            'body': ('{name} has joined the waitlist for "{tour}" on {departure}.\n\n'
                     'If you can take another traveller, adding a place will let them '
                     'book.'),
            'cta': 'Open the tour',
        },
        'ru': {
            'subject': 'Кто-то ждёт места — {tour}',
            'body': ('{name} записался(ась) в список ожидания на тур «{tour}» '
                     '{departure}.\n\n'
                     'Если можете взять ещё одного человека, добавьте место — и он '
                     'сможет забронировать.'),
            'cta': 'Открыть тур',
        },
    },
    'operator_verified': {
        'en': {
            'subject': 'Your guide account is verified',
            'body': ('Hi {name},\n\n'
                     'Your identity check has gone through. You can publish tours now.'),
            'cta': 'Go to my dashboard',
        },
        'ru': {
            'subject': 'Аккаунт гида подтверждён',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Проверка личности пройдена. Теперь вы можете публиковать туры.'),
            'cta': 'В личный кабинет',
        },
    },
    'operator_verification_rejected': {
        'en': {
            'subject': 'Your verification needs another look',
            'body': ('Hi {name},\n\n'
                     'We could not complete your identity check with the document you '
                     'sent.\n\n'
                     '{reason}\n\n'
                     'You can upload another one whenever you are ready.'),
            'cta': 'Upload a document',
        },
        'ru': {
            'subject': 'Проверку нужно пройти ещё раз',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Мы не смогли завершить проверку личности по присланному документу.\n\n'
                     '{reason}\n\n'
                     'Вы можете загрузить другой документ в любой момент.'),
            'cta': 'Загрузить документ',
        },
    },
    'tour_live': {
        'en': {
            'subject': 'Your tour is live: {tour}',
            'body': ('Hi {name},\n\n'
                     '"{tour}" has been approved and is now visible to travellers.'),
            'cta': 'View the listing',
        },
        'ru': {
            'subject': 'Тур опубликован: {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Тур «{tour}» одобрен и теперь виден путешественникам.'),
            'cta': 'Открыть страницу тура',
        },
    },
    'tour_changes_needed': {
        'en': {
            'subject': 'Changes needed on {tour}',
            'body': ('Hi {name},\n\n'
                     '"{tour}" is not ready to go live yet.\n\n'
                     '{reason}\n\n'
                     'Make the changes and submit it again — there is no limit on '
                     'resubmissions.'),
            'cta': 'Edit the tour',
        },
        'ru': {
            'subject': 'Нужны правки: {tour}',
            'body': ('Здравствуйте, {name}!\n\n'
                     'Тур «{tour}» пока не готов к публикации.\n\n'
                     '{reason}\n\n'
                     'Внесите правки и отправьте снова — количество попыток не '
                     'ограничено.'),
            'cta': 'Редактировать тур',
        },
    },
    'operator_new_review': {
        'en': {
            'subject': 'New review for {tour}: {rating}/5',
            'body': ('{name} left a {rating}-star review of "{tour}".\n\n'
                     '{message}\n\n'
                     'You can reply to it publicly.'),
            'cta': 'Read and reply',
        },
        'ru': {
            'subject': 'Новый отзыв о туре «{tour}»: {rating}/5',
            'body': ('{name} оставил(а) отзыв о туре «{tour}» — {rating} из 5.\n\n'
                     '{message}\n\n'
                     'Вы можете ответить на него публично.'),
            'cta': 'Прочитать и ответить',
        },
    },
    'operator_balance_unpaid': {
        'en': {
            'subject': 'Balance still unpaid — {tour}',
            'body': ('{name} has not paid the balance for "{tour}" departing '
                     '{departure}.\n\n'
                     'Reference: {ref}\n'
                     'Outstanding: {amount}\n\n'
                     'We are chasing it. You may want to message them as well.'),
            'cta': 'Open booking',
        },
        'ru': {
            'subject': 'Остаток так и не оплачен — {tour}',
            'body': ('{name} не оплатил(а) остаток по туру «{tour}», отправление '
                     '{departure}.\n\n'
                     'Номер брони: {ref}\n'
                     'К оплате: {amount}\n\n'
                     'Мы напоминаем. Возможно, стоит написать и вам.'),
            'cta': 'Открыть бронь',
        },
    },
    'operator_missed_booking': {
        'en': {
            'subject': 'A booking was cancelled because it was not confirmed — {tour}',
            'body': ('The booking by {name} for "{tour}" was cancelled automatically '
                     'because it was not confirmed in time.\n\n'
                     'Reference: {ref}\n\n'
                     'The traveller has been refunded in full.'),
            'cta': 'View bookings',
        },
        'ru': {
            'subject': 'Бронь отменена из-за неподтверждения — {tour}',
            'body': ('Бронь {name} на тур «{tour}» отменена автоматически, потому что '
                     'не была подтверждена вовремя.\n\n'
                     'Номер брони: {ref}\n\n'
                     'Путешественнику возвращена полная сумма.'),
            'cta': 'Открыть брони',
        },
    },
}
