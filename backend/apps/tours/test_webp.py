"""
WebP twins for tour photos.

Guides upload whatever came off their phone, so conversion has to happen for
them, on upload, every time. These tests hold that: the twins get written, the
originals are left alone, and a photo without a twin still has a URL.
"""
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.tours.models import Tour, TourPhoto
from apps.tours.serializers import TourPhotoSerializer
from apps.users.models import User


def a_jpeg(size=(1600, 1200)):
    from PIL import Image
    buf = BytesIO()
    Image.new('RGB', size, (90, 130, 90)).save(buf, format='JPEG', quality=92)
    return SimpleUploadedFile('photo.jpg', buf.getvalue(), content_type='image/jpeg')


class WebPTwinTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guide = User.objects.create_user(email='g@example.com', password='x',
                                             role=User.Role.OPERATOR)
        cls.tour = Tour.objects.create(operator=cls.guide, title='T', country='Georgia',
                                       destination='K', price_adult=Decimal('500'),
                                       currency='USD', status=Tour.Status.LIVE, max_group=8)

    def _photo(self):
        p = TourPhoto.objects.create(tour=self.tour, image=a_jpeg())
        p.make_thumbnail()
        p.make_webp()
        p.refresh_from_db()
        return p

    def test_a_webp_thumbnail_is_written(self):
        p = self._photo()
        self.assertTrue(p.thumbnail_webp)
        self.assertTrue(p.thumbnail_webp.name.endswith('.webp'))

    def test_a_webp_full_size_is_written(self):
        p = self._photo()
        self.assertTrue(p.image_webp)
        self.assertTrue(p.image_webp.name.endswith('.webp'))

    def test_the_original_upload_is_left_alone(self):
        """The JPEG is the fallback. Touching it would remove the safety net."""
        p = self._photo()
        self.assertTrue(p.image.name.endswith('.jpg'))
        self.assertTrue(p.thumbnail.name.endswith('.jpg'))

    def test_the_webp_is_smaller_than_the_jpeg_it_replaces(self):
        p = self._photo()
        self.assertLess(p.thumbnail_webp.size, p.thumbnail.size,
                        'if it is not smaller there is no reason to serve it')

    def test_the_full_size_copy_is_capped(self):
        """A 4000px phone photo is bytes nobody sees."""
        from PIL import Image
        p = TourPhoto.objects.create(tour=self.tour, image=a_jpeg((4000, 3000)))
        p.make_webp()
        p.refresh_from_db()
        p.image_webp.open()
        self.assertLessEqual(max(Image.open(p.image_webp).size), TourPhoto.FULL_MAX)
        self.assertLess(p.image_webp.size, p.image.size)

    def test_the_api_sends_both_formats(self):
        p = self._photo()
        data = TourPhotoSerializer(p).data
        self.assertTrue(data['thumb_url'].endswith('.jpg'))
        self.assertTrue(data['thumb_url_webp'].endswith('.webp'))
        self.assertTrue(data['url_webp'].endswith('.webp'))

    def test_a_photo_with_no_twin_still_has_urls(self):
        """
        Conversion is best-effort. A photo that never got one must degrade to
        the JPEG, not to a broken image.
        """
        p = TourPhoto.objects.create(tour=self.tour, image=a_jpeg())
        data = TourPhotoSerializer(p).data
        self.assertTrue(data['url'])
        self.assertTrue(data['thumb_url'], 'thumb_url falls back to the original')
        self.assertEqual(data['thumb_url_webp'], '')
        self.assertEqual(data['url_webp'], '')

    def test_the_backfill_command_picks_up_photos_missing_a_twin(self):
        from django.core.management import call_command
        p = TourPhoto.objects.create(tour=self.tour, image=a_jpeg())
        call_command('generate_thumbnails', verbosity=0)
        p.refresh_from_db()
        self.assertTrue(p.thumbnail_webp)
        self.assertTrue(p.image_webp)
