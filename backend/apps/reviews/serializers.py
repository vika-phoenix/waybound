"""
apps/reviews/serializers.py
"""
from rest_framework import serializers
from django.utils import timezone
from .models import TourReview


class TourReviewSerializer(serializers.ModelSerializer):
    tourist_name    = serializers.SerializerMethodField()
    tour_title      = serializers.SerializerMethodField()
    tour_slug       = serializers.SlugRelatedField(source='tour', slug_field='slug', read_only=True)
    hero_photo_url  = serializers.SerializerMethodField()
    guide_name      = serializers.SerializerMethodField()

    class Meta:
        model  = TourReview
        fields = [
            'id', 'tour', 'tour_slug', 'tour_title', 'rating', 'title', 'body',
            'operator_reply', 'replied_at',
            'status', 'created_at', 'tourist_name',
            'hero_photo_url', 'guide_name',
        ]
        read_only_fields = ['id', 'status', 'operator_reply', 'replied_at', 'created_at',
                            'tourist_name', 'tour_title', 'tour_slug', 'hero_photo_url', 'guide_name']

    def get_tourist_name(self, obj):
        u = obj.tourist
        name = ((u.first_name or '') + ' ' + (u.last_name or '')).strip()
        return name or u.email

    def get_tour_title(self, obj):
        return obj.tour.title

    def get_hero_photo_url(self, obj):
        photo = obj.tour.photos.filter(order=0).first() or obj.tour.photos.first()
        if not photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(photo.image.url) if request else photo.image.url

    def get_guide_name(self, obj):
        op = obj.tour.operator
        name = ((op.first_name or '') + ' ' + (op.last_name or '')).strip()
        return name or op.email

    def validate_tour(self, value):
        return value

    def create(self, validated_data):
        validated_data['tourist'] = self.context['request'].user
        return super().create(validated_data)


class TourReviewWriteSerializer(TourReviewSerializer):
    """Accepts tour as slug string for ease of use from the frontend."""
    tour_slug   = serializers.SlugField(write_only=True)
    booking_ref = serializers.CharField(write_only=True, required=False, allow_blank=True)
    tour        = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta(TourReviewSerializer.Meta):
        fields = ['id', 'tour_slug', 'booking_ref', 'tour', 'rating', 'title', 'body', 'tourist_name',
                  'operator_reply', 'replied_at', 'status', 'created_at']

    def validate(self, data):
        import datetime
        from apps.tours.models import Tour
        from apps.bookings.models import Booking
        slug = data.pop('tour_slug')
        booking_ref = data.pop('booking_ref', '')
        try:
            data['tour'] = Tour.objects.get(slug=slug)
        except Tour.DoesNotExist:
            raise serializers.ValidationError({'tour_slug': 'Tour not found.'})

        user = self.context['request'].user

        # Tourist must have a confirmed or completed booking for this tour
        bookings = Booking.objects.filter(
            tourist=user, tour=data['tour'],
            status__in=[Booking.Status.CONFIRMED, Booking.Status.COMPLETED],
        ).select_related('departure')
        if not bookings.exists():
            raise serializers.ValidationError('You must have a confirmed booking to review this tour.')

        # Tour must have ended (departure end date must be in the past, in tour timezone)
        import zoneinfo
        tz_name = getattr(data['tour'], 'timezone', '') or 'Europe/Moscow'
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except (KeyError, Exception):
            tz = zoneinfo.ZoneInfo('Europe/Moscow')
        today = timezone.now().astimezone(tz).date()
        tour_ended = False
        for bk in bookings:
            if bk.status == 'completed' and getattr(bk, 'balance_status', None) == 'paid':
                tour_ended = True
                break
            if bk.departure_date:
                if bk.departure and bk.departure.end_date:
                    end_date = bk.departure.end_date
                else:
                    tour_days = getattr(bk.tour, 'days', 1) or 1
                    end_date = bk.departure_date + datetime.timedelta(days=tour_days - 1)
                if today >= end_date:
                    tour_ended = True
                    break
        if not tour_ended:
            raise serializers.ValidationError('You can only review a tour after it has ended.')

        # Link to booking if ref provided
        if booking_ref:
            try:
                data['booking'] = Booking.objects.get(
                    reference=booking_ref, tourist=user
                )
            except Booking.DoesNotExist:
                pass

        # One review per tourist per tour
        if TourReview.objects.filter(tourist=user, tour=data['tour']).exists():
            raise serializers.ValidationError('You have already reviewed this tour.')
        return data
