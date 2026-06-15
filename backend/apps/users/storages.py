"""
Storage for sensitive uploads (operator ID / guide credentials).

These must stay PRIVATE even after the main media bucket is made public for
tour photos. In prod we put them in a separate private R2 bucket and serve
them via short-lived presigned URLs; in dev (no R2 configured) they fall back
to the local filesystem. Used as a callable on the model field so it resolves
per-environment without baking a bucket name into migrations.
"""
from django.conf import settings
from django.core.files.storage import FileSystemStorage


def private_media_storage():
    bucket = getattr(settings, 'R2_PRIVATE_BUCKET', '')
    if bucket:
        from storages.backends.s3boto3 import S3Boto3Storage
        return S3Boto3Storage(
            bucket_name=bucket,
            querystring_auth=True,   # presigned — private, time-limited
            custom_domain=None,      # never serve these via the public CDN domain
            default_acl=None,
            file_overwrite=False,
        )
    return FileSystemStorage()
