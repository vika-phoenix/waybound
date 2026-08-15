"""
Verification scans are deleted once the decision they supported is old enough.

A passport is needed to decide whether to verify a guide, not to keep
afterwards. Holding them indefinitely is personal data with no ongoing purpose
and a breach would expose it.

Two rules these lock in: a pending document is never purged however old — an
undecided application still needs the thing it is waiting on — and the row
always survives, so the verification decision stays auditable after the image
is gone.
"""
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.users.models import User, VerificationDocument

PDF = b'%PDF-1.4 fake scan'


@override_settings(VERIFICATION_DOC_RETENTION_DAYS=90)
class RetentionTest(TestCase):
    def setUp(self):
        self.guide = User.objects.create_user(
            email='r@example.com', password='x', role=User.Role.OPERATOR)

    def _doc(self, status='approved', reviewed_days_ago=None):
        d = VerificationDocument.objects.create(
            operator=self.guide, status=status,
            reviewed_at=(timezone.now() - timedelta(days=reviewed_days_ago)
                         if reviewed_days_ago is not None else None))
        d.document.save(f'scan{d.pk}.pdf', ContentFile(PDF), save=True)
        return d

    def test_an_old_decided_document_loses_its_file_but_not_its_record(self):
        d = self._doc('approved', reviewed_days_ago=120)
        call_command('purge_verification_documents')
        d.refresh_from_db()
        self.assertFalse(d.document, 'the scan should be gone')
        self.assertIsNotNone(d.purged_at)
        self.assertEqual(d.status, 'approved', 'the decision stays on record')
        self.assertTrue(VerificationDocument.objects.filter(pk=d.pk).exists())

    def test_a_rejected_document_is_purged_too(self):
        d = self._doc('rejected', reviewed_days_ago=120)
        call_command('purge_verification_documents')
        d.refresh_from_db()
        self.assertFalse(d.document)

    def test_a_recent_decision_is_left_alone(self):
        d = self._doc('approved', reviewed_days_ago=10)
        call_command('purge_verification_documents')
        d.refresh_from_db()
        self.assertTrue(d.document)
        self.assertIsNone(d.purged_at)

    def test_a_pending_document_is_never_purged_however_old(self):
        """It is still waiting on a decision — deleting it destroys the work."""
        d = self._doc('pending', reviewed_days_ago=None)
        d.submitted_at = timezone.now() - timedelta(days=900)
        d.save(update_fields=['submitted_at'])
        call_command('purge_verification_documents')
        d.refresh_from_db()
        self.assertTrue(d.document)

    def test_a_dry_run_changes_nothing(self):
        d = self._doc('approved', reviewed_days_ago=200)
        call_command('purge_verification_documents', dry_run=True)
        d.refresh_from_db()
        self.assertTrue(d.document)
        self.assertIsNone(d.purged_at)

    def test_purging_twice_is_harmless(self):
        d = self._doc('approved', reviewed_days_ago=200)
        call_command('purge_verification_documents')
        d.refresh_from_db()
        first = d.purged_at
        call_command('purge_verification_documents')
        d.refresh_from_db()
        self.assertEqual(d.purged_at, first, 'the timestamp must not be rewritten')

    @override_settings(VERIFICATION_DOC_RETENTION_DAYS=0)
    def test_retention_can_be_switched_off(self):
        d = self._doc('approved', reviewed_days_ago=900)
        call_command('purge_verification_documents')
        d.refresh_from_db()
        self.assertTrue(d.document)

    def test_the_window_is_configurable_per_run(self):
        d = self._doc('approved', reviewed_days_ago=40)
        call_command('purge_verification_documents')
        d.refresh_from_db()
        self.assertTrue(d.document, '40 days is inside the 90-day default')
        call_command('purge_verification_documents', days=30)
        d.refresh_from_db()
        self.assertFalse(d.document, 'and outside a 30-day window')

    def test_the_admin_says_deleted_rather_than_showing_a_dash(self):
        """A routine purge must not read as data loss."""
        from apps.users.admin import VerificationDocumentAdmin
        from django.contrib.admin.sites import AdminSite
        d = self._doc('approved', reviewed_days_ago=200)
        call_command('purge_verification_documents')
        d.refresh_from_db()
        rendered = VerificationDocumentAdmin(VerificationDocument, AdminSite()).document_link(d)
        self.assertIn('retention', rendered)
        self.assertNotEqual(rendered, '—')
