"""
Backfill thumbnails for TourPhotos that don't have one yet.

Run after deploying the thumbnail feature (on the server that has the real
media storage / R2 credentials):

    python manage.py generate_thumbnails          # only photos missing a thumb
    python manage.py generate_thumbnails --all    # regenerate every thumbnail

New uploads generate their thumbnail automatically; this is just for photos
that were uploaded before the feature existed.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from apps.tours.models import TourPhoto


class Command(BaseCommand):
    help = 'Generate thumbnails for existing tour photos.'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true',
                            help='Regenerate thumbnails even if one already exists.')

    def handle(self, *args, **opts):
        qs = TourPhoto.objects.all()
        if not opts['all']:
            qs = qs.filter(Q(thumbnail='') | Q(thumbnail__isnull=True)
                           | Q(thumbnail_webp='') | Q(thumbnail_webp__isnull=True)
                           | Q(image_webp='') | Q(image_webp__isnull=True))

        total = qs.count()
        self.stdout.write(f'Generating thumbnails for {total} photo(s)…')
        done = failed = 0
        for photo in qs.iterator():
            try:
                photo.make_thumbnail()
                photo.make_webp()
                done += 1
                self.stdout.write(f'  OK  {photo.tour.slug} #{photo.order}')
            except Exception as e:
                failed += 1
                self.stderr.write(f'  FAIL photo {photo.id}: {e}')
        self.stdout.write(self.style.SUCCESS(f'Done: {done} generated, {failed} failed.'))
