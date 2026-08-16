"""
apps/users/emails.py — admin notifications for the moderation queue.

An operator uploading an ID document used to notify nobody: the record was
created, the operator was told "we will review within 48 hours", and no one
found out until someone happened to open the admin. Silent on both ends — the
operator waits, the admin does not know anyone is waiting.

Failures here must never break the upload itself. A verification document that
saved but whose notification bounced is recoverable; an upload that 500s
because the mail server was down is not.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _admin_recipient():
    return (getattr(settings, 'ADMIN_NOTIFICATION_EMAIL', None)
            or getattr(settings, 'DEFAULT_FROM_EMAIL', None))


def notify_admin_verification_submitted(user, doc_type='identity'):
    """Tell the admin an operator is waiting on identity verification."""
    admin_email = _admin_recipient()
    if not admin_email:
        logger.warning('No ADMIN_NOTIFICATION_EMAIL — verification upload not announced.')
        return False

    label = 'guide credential' if doc_type == 'credential' else 'identity document'
    who = user.full_name or user.email
    subject = f'[Admin] Verification submitted — {who}'
    body = (
        f'An operator has uploaded a {label} and is waiting to be verified.\n'
        f'They cannot submit any tour for review until you approve them.\n\n'
        f'Operator: {who}\n'
        f'Email:    {user.email}\n'
        f'Phone:    {getattr(user, "phone", "") or "-"}\n'
        f'Company:  {getattr(user, "company_name", "") or "-"}\n'
        f'Country:  {getattr(user, "country", "") or "-"}\n\n'
        f'Review the document, then tick "is verified" on the user:\n'
        f'/admin/users/user/{user.pk}/change/\n'
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [admin_email],
                  fail_silently=False)
        logger.info('Verification-submitted notice sent for %s', user.email)
        return True
    except Exception as exc:
        logger.error('Could not send verification notice for %s: %s', user.email, exc)
        return False


def notify_operator_verification_result(user, approved):
    """
    Tell the operator the outcome. Without this the wait has no end from their
    side — they are blocked from submitting tours and never learn why it lifted.
    """
    if not user.email:
        return False

    from apps.mail import lang_for, send

    lang = lang_for(user)
    site = getattr(settings, 'FRONTEND_URL', '')
    name = user.first_name or ('Гид' if lang == 'ru' else 'there')
    if approved:
        return send(user.email, 'operator_verified', lang,
                    url=f'{site}/operator-dashboard.html', name=name)
    return send(user.email, 'operator_verification_rejected', lang,
                url=f'{site}/settings.html#verification', name=name,
                reason=('Документ не удалось разобрать — обычно дело в качестве '
                        'снимка или в том, что видна не вся страница.'
                        if lang == 'ru' else
                        'The document could not be read clearly — usually that means '
                        'the photo quality, or part of the page being cut off.'))

def notify_admin_operator_upgrade(user):
    """
    Tell the admin an existing traveller has converted to a guide account.

    They arrive able to build drafts but unverified, so they will be stopped at
    submission until someone approves their ID.
    """
    admin_email = _admin_recipient()
    if not admin_email:
        logger.warning('No ADMIN_NOTIFICATION_EMAIL - operator upgrade not announced.')
        return False

    who = user.full_name or user.email
    subject = f'[Admin] Traveller upgraded to guide - {who}'
    body = (
        f'{who} ({user.email}) converted their traveller account into a guide '
        f'account.\n\n'
        f'They are NOT verified yet, so they cannot submit any tour until you '
        f'approve them.\n\n'
        f'/admin/users/user/{user.pk}/change/\n'
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [admin_email],
                  fail_silently=False)
        logger.info('Operator-upgrade notice sent for %s', user.email)
        return True
    except Exception as exc:
        logger.error('Could not send upgrade notice for %s: %s', user.email, exc)
        return False
