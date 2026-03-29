"""
apps/tours/serializers.py  —  Task 18

Serializers for:
  TourListSerializer     — lightweight card view (adventures grid)
  TourDetailSerializer   — full tour page
  TourWriteSerializer    — operator create / edit (nested write)
  DepartureDateSerializer
  SavedTourSerializer
"""
from rest_framework import serializers
from django.utils import timezone
from .models import Tour, DepartureDate, DayItinerary, StayBlock, CancelPeriod, TourPhoto, TourFAQ, SavedTour, PropertyPhoto, WaitlistEntry  # noqa: F401


# ── Nested read serializers ───────────────────────────────────────────────────

class DepartureDateSerializer(serializers.ModelSerializer):
    price        = serializers.ReadOnlyField()
    is_soft_full = serializers.SerializerMethodField()

    class Meta:
        model  = DepartureDate
        fields = ['id', 'start_date', 'end_date', 'spots_total', 'spots_left', 'status', 'price', 'notes', 'is_soft_full']

    def get_is_soft_full(self, obj):
        """True when spots_left=0 but some confirmed bookings still have unpaid balances."""
        if obj.spots_left > 0:
            return False
        from apps.bookings.models import Booking
        return obj.bookings.filter(
            status=Booking.Status.CONFIRMED,
            balance_status='pending',
        ).exists()


class DayItinerarySerializer(serializers.ModelSerializer):
    class Meta:
        model  = DayItinerary
        fields = ['day_number', 'title', 'description', 'meals', 'elevation']


class PropertyPhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model  = PropertyPhoto
        fields = ['id', 'url', 'order', 'caption']

    def get_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return ''


class StayBlockSerializer(serializers.ModelSerializer):
    photos = PropertyPhotoSerializer(many=True, read_only=True)

    class Meta:
        model  = StayBlock
        fields = ['id', 'property_name', 'property_type', 'comfort_level', 'night_from', 'night_to', 'room_types', 'photos']


class CancelPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CancelPeriod
        fields = ['days_before_min', 'days_before_max', 'penalty_pct', 'label']


class TourPhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model  = TourPhoto
        fields = ['id', 'url', 'order', 'caption']

    def get_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return ''


class TourFAQSerializer(serializers.ModelSerializer):
    class Meta:
        model  = TourFAQ
        fields = ['order', 'question', 'answer']


# ── Public list serializer (card grid) ───────────────────────────────────────

class TourListSerializer(serializers.ModelSerializer):
    guide_display      = serializers.SerializerMethodField()
    operator_photo_url = serializers.SerializerMethodField()
    hero_photo_url     = serializers.SerializerMethodField()
    price              = serializers.DecimalField(source='price_adult', max_digits=10, decimal_places=2)
    next_departure     = serializers.SerializerMethodField()
    spots_left         = serializers.ReadOnlyField(source='spots_left_for_next_departure')
    saved_count        = serializers.SerializerMethodField()
    is_saved           = serializers.SerializerMethodField()
    is_guaranteed      = serializers.SerializerMethodField()

    class Meta:
        model  = Tour
        fields = [
            'slug', 'title', 'destination', 'country', 'region', 'category', 'categories', 'difficulty',
            'days', 'price', 'currency', 'timezone', 'max_group', 'rating', 'review_count',
            'tags', 'guide_display', 'operator_photo_url', 'hero_photo_url',
            'next_departure', 'spots_left', 'tour_type',
            'saved_count', 'is_saved', 'is_guaranteed',
        ]

    def get_guide_display(self, obj):
        return obj.operator.full_name or obj.operator.email

    def get_operator_photo_url(self, obj):
        if not obj.operator.avatar:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.operator.avatar.url) if request else obj.operator.avatar.url

    def get_hero_photo_url(self, obj):
        photo = obj.hero_photo
        if not photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(photo.image.url) if request else photo.image.url

    def get_next_departure(self, obj):
        nxt = obj.departures.filter(
            status__in=[DepartureDate.Status.OPEN, DepartureDate.Status.GUARANTEED],
            start_date__gte=timezone.now().date(),
        ).order_by('start_date').first()
        if not nxt:
            return None
        return {'start': str(nxt.start_date), 'end': str(nxt.end_date), 'spots_left': nxt.spots_left}

    def get_is_guaranteed(self, obj):
        """True if the tour has at least one upcoming departure marked as guaranteed."""
        return obj.departures.filter(
            status=DepartureDate.Status.GUARANTEED,
            start_date__gte=timezone.now().date(),
        ).exists()

    def get_saved_count(self, obj):
        return obj.saved_by.count()

    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.saved_by.filter(tourist=request.user).exists()
        return False


# ── Full detail serializer ────────────────────────────────────────────────────

class TourDetailSerializer(TourListSerializer):
    departures    = DepartureDateSerializer(many=True, read_only=True)
    itinerary     = DayItinerarySerializer(many=True, read_only=True)
    stays         = StayBlockSerializer(many=True, read_only=True)
    cancel_policy = CancelPeriodSerializer(many=True, read_only=True)
    photos        = TourPhotoSerializer(many=True, read_only=True)
    faqs          = TourFAQSerializer(many=True, read_only=True)
    operator_bio  = serializers.SerializerMethodField()

    def get_operator_bio(self, obj):
        return obj.operator.bio or ''

    class Meta(TourListSerializer.Meta):
        fields = TourListSerializer.Meta.fields + [
            'status',
            'operator_bio',
            'description', 'highlights', 'includes', 'excludes',
            'requirements', 'meeting_point', 'meeting_time', 'end_point',
            'latitude', 'longitude', 'timezone', 'min_group',
            'price_child', 'booking_count',
            'language', 'languages', 'difficulty_note', 'extras',
            'min_age', 'max_age', 'is_private',
            'video_url', 'getting_there', 'organiser_note',
            'departures', 'itinerary', 'stays', 'cancel_policy',
            'photos', 'faqs', 'created_at',
            'deposit_pct', 'balance_due_days',
        ]


# ── Nested write helpers ──────────────────────────────────────────────────────

class DepartureDateWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DepartureDate
        fields = ['start_date', 'end_date', 'spots_total', 'spots_left', 'price_override', 'notes']

    def validate(self, data):
        today = timezone.now().date()
        if data.get('start_date') and data['start_date'] < today:
            raise serializers.ValidationError({'start_date': 'Departure date cannot be in the past.'})
        if data.get('end_date') and data.get('start_date') and data['end_date'] < data['start_date']:
            raise serializers.ValidationError('end_date must be after start_date')
        return data


class DayItineraryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DayItinerary
        fields = ['day_number', 'title', 'description', 'meals', 'elevation']


class StayBlockWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = StayBlock
        fields = ['property_name', 'property_type', 'comfort_level', 'night_from', 'night_to', 'room_types']

    def validate(self, data):
        if data.get('night_to', 0) < data.get('night_from', 1):
            raise serializers.ValidationError('night_to must be >= night_from')
        return data


class CancelPeriodWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CancelPeriod
        fields = ['days_before_min', 'days_before_max', 'penalty_pct', 'label']


class TourFAQWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = TourFAQ
        fields = ['order', 'question', 'answer']


# ── Operator write serializer (create + edit) ─────────────────────────────────

class TourWriteSerializer(serializers.ModelSerializer):
    """
    Accepts nested lists for departures, itinerary, stays, cancel_policy, faqs.
    Photos are handled separately via TourPhotoUploadView (multipart).
    """
    departures    = DepartureDateWriteSerializer(many=True, required=False)
    itinerary     = DayItineraryWriteSerializer(many=True, required=False)
    stays         = StayBlockWriteSerializer(many=True, required=False)
    cancel_policy = CancelPeriodWriteSerializer(many=True, required=False)
    faqs          = TourFAQWriteSerializer(many=True, required=False)

    class Meta:
        model  = Tour
        fields = [
            'title', 'category', 'categories', 'difficulty', 'tour_type',
            'country', 'destination', 'region',
            'days', 'price_adult', 'price_child', 'currency', 'max_group', 'min_group',
            'description', 'highlights', 'includes', 'excludes',
            'requirements', 'meeting_point', 'meeting_time', 'end_point',
            'latitude', 'longitude', 'timezone', 'tags',
            'language', 'languages', 'difficulty_note', 'extras',
            'min_age', 'max_age', 'is_private',
            'video_url', 'getting_there', 'organiser_note',
            'departures', 'itinerary', 'stays', 'cancel_policy', 'faqs',
            'deposit_pct', 'balance_due_days',
        ]
        extra_kwargs = {
            'country':     {'required': False, 'allow_blank': True},
            'destination': {'required': False, 'allow_blank': True},
            'region':      {'required': False, 'allow_blank': True},
        }

    def _save_nested(self, tour, nested_data, model_class, serializer_class):
        """Delete existing rows, recreate from submitted data."""
        from django.db import IntegrityError
        model_class.objects.filter(tour=tour).delete()
        seen_dates = set()
        for item_data in nested_data:
            # Deduplicate departure dates — skip exact duplicates silently
            date_key = item_data.get('start_date')
            if date_key is not None:
                if date_key in seen_dates:
                    continue
                seen_dates.add(date_key)
            try:
                model_class.objects.create(tour=tour, **item_data)
            except IntegrityError:
                raise serializers.ValidationError(
                    {'departures': [f'Duplicate departure date: {date_key}. Each departure date must be unique.']}
                )

    def create(self, validated_data):
        departures    = validated_data.pop('departures', [])
        itinerary     = validated_data.pop('itinerary', [])
        stays         = validated_data.pop('stays', [])
        cancel_policy = validated_data.pop('cancel_policy', [])
        faqs          = validated_data.pop('faqs', [])

        tour = Tour.objects.create(
            operator=self.context['request'].user,
            **validated_data,
        )
        self._write_nested(tour, departures, itinerary, stays, cancel_policy, faqs)
        return tour

    def update(self, instance, validated_data):
        departures    = validated_data.pop('departures', None)
        itinerary     = validated_data.pop('itinerary', None)
        stays         = validated_data.pop('stays', None)
        cancel_policy = validated_data.pop('cancel_policy', None)
        faqs          = validated_data.pop('faqs', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if departures is not None:
            self._save_nested(instance, departures, DepartureDate, DepartureDateWriteSerializer)
        if itinerary is not None:
            self._save_nested(instance, itinerary, DayItinerary, DayItineraryWriteSerializer)
        if stays is not None:
            self._update_stays(instance, stays)
        if cancel_policy is not None:
            self._save_nested(instance, cancel_policy, CancelPeriod, CancelPeriodWriteSerializer)
        if faqs is not None:
            self._save_nested(instance, faqs, TourFAQ, TourFAQWriteSerializer)

        return instance

    def _update_stays(self, tour, stays_data):
        """Update stays in-place matched by night_from to preserve PropertyPhotos."""
        existing = {s.night_from: s for s in StayBlock.objects.filter(tour=tour)}
        incoming_nights = {d['night_from'] for d in stays_data}

        # Remove stays no longer in payload
        for night_from, stay in existing.items():
            if night_from not in incoming_nights:
                stay.delete()

        # Update existing or create new
        for data in stays_data:
            night_from = data['night_from']
            if night_from in existing:
                stay = existing[night_from]
                for attr, val in data.items():
                    setattr(stay, attr, val)
                stay.save()
            else:
                StayBlock.objects.create(tour=tour, **data)

    def _write_nested(self, tour, departures, itinerary, stays, cancel_policy, faqs):
        for d in departures:
            DepartureDate.objects.create(tour=tour, **d)
        for i, day in enumerate(itinerary):
            DayItinerary.objects.create(tour=tour, **day)
        for s in stays:
            StayBlock.objects.create(tour=tour, **s)
        for c in cancel_policy:
            CancelPeriod.objects.create(tour=tour, **c)
        for i, faq in enumerate(faqs):
            faq.setdefault('order', i)
            TourFAQ.objects.create(tour=tour, **faq)


# ── Saved tour serializer ─────────────────────────────────────────────────────

class SavedTourSerializer(serializers.ModelSerializer):
    tour_detail = TourListSerializer(source='tour', read_only=True)

    class Meta:
        model  = SavedTour
        fields = ['id', 'tour_detail', 'created_at']


# ── Waitlist serializer ───────────────────────────────────────────────────────

class WaitlistEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model  = WaitlistEntry
        fields = ['email', 'name', 'departure_label']


# ── Operator dashboard serializers ────────────────────────────────────────────

class OperatorTourListSerializer(serializers.ModelSerializer):
    """Slim serializer for operator's own tour management."""
    booking_count   = serializers.ReadOnlyField()
    next_departure  = serializers.SerializerMethodField()
    hero_photo_url  = serializers.SerializerMethodField()

    class Meta:
        model  = Tour
        fields = [
            'slug', 'title', 'status', 'category', 'categories', 'days',
            'price_adult', 'currency', 'max_group',
            'rating', 'review_count', 'booking_count',
            'is_private', 'hero_photo_url', 'next_departure',
            'created_at', 'updated_at',
        ]

    def get_next_departure(self, obj):
        nxt = obj.departures.filter(
            status=DepartureDate.Status.OPEN,
            start_date__gte=timezone.now().date(),
        ).order_by('start_date').first()
        return {'start': str(nxt.start_date), 'spots_left': nxt.spots_left} if nxt else None

    def get_hero_photo_url(self, obj):
        photo = obj.hero_photo
        if not photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(photo.image.url) if request else photo.image.url
