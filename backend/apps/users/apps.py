from django.apps import AppConfig
from django.core.checks import Warning, register


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'
    verbose_name = 'Users'

    def ready(self):
        register(check_private_document_storage)


def check_private_document_storage(app_configs, **kwargs):
    """
    Refuse to let identity documents land on a disposable disk in silence.

    `private_media_storage()` falls back to FileSystemStorage when
    R2_PRIVATE_BUCKET is unset. That is right for local development and wrong
    everywhere else: a container filesystem does not survive a deploy, so a
    guide's passport scan is written, shown as uploaded, and gone by the next
    release — with the admin link 404ing and no error anywhere.

    Keyed on whether object storage is configured at all rather than on DEBUG,
    which Django forces to False under test — so this stays quiet in local
    development and during tests, and speaks up exactly where it matters: an
    environment already using R2 for public media but missing the private
    bucket for documents.

    A warning rather than an error, because failing the check would block a
    deploy on a misconfiguration that is recoverable. It prints on every
    management command, which is loud enough to notice and cheap to fix.
    """
    from django.conf import settings

    uses_object_storage = bool(getattr(settings, 'AWS_S3_ENDPOINT_URL', ''))
    if not uses_object_storage or getattr(settings, 'R2_PRIVATE_BUCKET', ''):
        return []
    return [Warning(
        'Verification documents are being written to the local filesystem.',
        hint=('Set R2_PRIVATE_BUCKET to a private R2 bucket. Without it, uploaded '
              'identity documents go to the container disk and are lost on the next '
              'deploy. That bucket must NOT have a public custom domain attached — '
              'it is served through short-lived presigned URLs.'),
        id='users.W001',
    )]