"""
Delete verification scans once the decision they supported has been made.

A passport is needed to decide whether to verify a guide, not to keep
afterwards. Holding them indefinitely is personal data you have no ongoing use
for and a breach would expose — GDPR calls this storage limitation.

Only the file goes; the row stays, so who was verified, when, and against what
kind of document remains on record.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.users.models import VerificationDocument


class Command(BaseCommand):
    help = 'Delete verification document files older than the retention period.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=None,
            help='Override VERIFICATION_DOC_RETENTION_DAYS for this run.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='List what would be deleted without touching anything.')

    def handle(self, *args, **opts):
        days = opts['days'] or getattr(settings, 'VERIFICATION_DOC_RETENTION_DAYS', 90)
        if days <= 0:
            self.stdout.write('Retention disabled (days <= 0) — nothing to do.')
            return

        cutoff = timezone.now() - timedelta(days=days)
        # Pending documents are never touched, however old: an undecided
        # application still needs the thing it is waiting on. Only a decision
        # starts the clock.
        due = VerificationDocument.objects.filter(
            reviewed_at__isnull=False,
            reviewed_at__lt=cutoff,
            purged_at__isnull=True,
        ).exclude(document='').select_related('operator')

        if not due.exists():
            self.stdout.write(f'Nothing to purge (retention {days} days).')
            return

        purged = failed = 0
        for doc in due:
            label = f'{doc.operator.email} · {doc.doc_type} · reviewed {doc.reviewed_at:%Y-%m-%d}'
            if opts['dry_run']:
                self.stdout.write(f'would purge: {label}')
                continue
            try:
                if doc.purge_file():
                    purged += 1
                    self.stdout.write(f'purged: {label}')
            except Exception as exc:
                # One unreachable file must not stop the rest being cleaned up.
                failed += 1
                self.stderr.write(f'FAILED {label}: {exc}')

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'Dry run — {due.count()} document(s) are past {days} days.'))
        else:
            msg = f'Purged {purged} document file(s) older than {days} days.'
            self.stdout.write(self.style.SUCCESS(msg))
            if failed:
                self.stderr.write(f'{failed} could not be deleted; they stay queued for next run.')
