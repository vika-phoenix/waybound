"""
apps/bookings/serializers.py  —  Task 18
"""
from rest_framework import serializers
from .models import Booking, EnquiryMessage, EnquiryReply
from apps.tours.serializers import TourListSerializer


class BookingCreateSerializer(serializers.ModelSerializer):
    """
    POST /api/v1/bookings/
    Submitted by tourist after filling the booking form.
    """
    tour_slug    = serializers.SlugField(write_only=True)
    departure_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    extras_cost          = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    room_supplement_cost = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)

    class Meta:
        model  = Booking
        fields = [
            'tour_slug',
            'departure_id',
            'adults', 'children', 'infants',
            'first_name', 'last_name', 'email', 'phone', 'country',
            'emergency_name', 'emergency_phone', 'notes',
            'room_preference', 'selected_extras',
            'extras_cost', 'room_supplement_cost',
            'departure_date',
        ]

    def validate_tour_slug(self, value):
        from apps.tours.models import Tour
        try:
            return Tour.objects.get(slug=value, status='live')
        except Tour.DoesNotExist:
            raise serializers.ValidationError('Tour not found or not available.')

    def validate(self, data):
        tour = data['tour_slug']  # already a Tour instance after validate_tour_slug
        adults = data.get('adults', 1)
        children = data.get('children', 0)
        if adults + children > tour.max_group:
            raise serializers.ValidationError(
                f'Group size exceeds tour maximum of {tour.max_group}.'
            )

        # Resolve departure FK if ID provided
        dep_id = data.pop('departure_id', None)
        if dep_id:
            from apps.tours.models import DepartureDate
            try:
                data['departure'] = DepartureDate.objects.get(pk=dep_id, tour=tour)
            except DepartureDate.DoesNotExist:
                pass  # ignore bad IDs silently — departure_date string is still set

        # Check group size against remaining spots on the departure
        dep = data.get('departure')
        if dep and dep.spots_left < (adults + children):
            raise serializers.ValidationError(
                f'Only {dep.spots_left} spot(s) remaining on this departure — '
                f'not enough for a group of {adults + children}.'
            )

        return data

    def create(self, validated_data):
        tour = validated_data.pop('tour_slug')
        adults   = validated_data.get('adults', 1)
        children = validated_data.get('children', 0)

        price_adult = float(tour.price_adult)
        price_child = float(tour.price_child_effective)
        extras_cost = float(validated_data.get('extras_cost', 0) or 0)
        room_supp   = float(validated_data.get('room_supplement_cost', 0) or 0)
        total = (adults * price_adult) + (children * price_child) + extras_cost + room_supp

        # Snapshot the cancellation policy at booking time so operator edits
        # cannot retroactively change the terms the tourist agreed to.
        from apps.bookings.views import PLATFORM_DEFAULT_CANCEL_POLICY
        policy_snapshot = [
            {
                'days_before_min': cp.days_before_min,
                'days_before_max': cp.days_before_max,
                'penalty_pct':     cp.penalty_pct,
                'label':           cp.label,
            }
            for cp in tour.cancel_policy.all()
        ] or PLATFORM_DEFAULT_CANCEL_POLICY

        booking = Booking.objects.create(
            tourist                = self.context['request'].user if self.context['request'].user.is_authenticated else None,
            tour                   = tour,
            price_adult            = price_adult,
            price_child            = price_child,
            total_price            = total,
            currency               = tour.currency,
            cancel_policy_snapshot = policy_snapshot,
            **validated_data,
        )
        return booking


class BookingDetailSerializer(serializers.ModelSerializer):
    """Full booking detail — tourist dashboard view."""
    tour_detail      = TourListSerializer(source='tour', read_only=True)
    guests           = serializers.ReadOnlyField()
    price_per_person = serializers.ReadOnlyField()
    balance_due      = serializers.ReadOnlyField()

    class Meta:
        model  = Booking
        fields = [
            'id', 'reference', 'status',
            'adults', 'children', 'infants', 'guests',
            'first_name', 'last_name', 'email', 'phone', 'country',
            'emergency_name', 'emergency_phone', 'notes',
            'room_preference', 'selected_extras',
            'cancel_policy_snapshot',
            'departure_date',
            'price_adult', 'price_child', 'total_price',
            'extras_cost', 'room_supplement_cost',
            'price_per_person', 'deposit_paid', 'deposit_status', 'balance_due', 'balance_paid',
            'balance_status', 'balance_due_date', 'currency',
            'payment_method', 'yookassa_payment_id', 'balance_payment_id',
            'refund_amount', 'refund_status',
            'tour_detail',
            'created_at', 'confirmed_at', 'cancelled_at',
        ]


class OperatorBookingSerializer(serializers.ModelSerializer):
    """Bookings on the operator dashboard — includes traveller contact."""
    tour_slug        = serializers.CharField(source='tour.slug', read_only=True)
    tour_title       = serializers.CharField(source='tour.title', read_only=True)
    guests           = serializers.ReadOnlyField()
    price_per_person = serializers.ReadOnlyField()
    balance_due      = serializers.ReadOnlyField()
    enquiry_id       = serializers.SerializerMethodField()
    msg_unread       = serializers.SerializerMethodField()

    class Meta:
        model  = Booking
        fields = [
            'id', 'reference', 'status',
            'tour_slug', 'tour_title',
            'adults', 'children', 'infants', 'guests',
            'first_name', 'last_name', 'email', 'phone', 'country',
            'emergency_name', 'emergency_phone', 'notes',
            'room_preference', 'selected_extras',
            'departure_date',
            'price_per_person', 'total_price', 'extras_cost', 'room_supplement_cost',
            'deposit_paid', 'balance_due',
            'balance_paid', 'balance_status', 'balance_due_date', 'currency',
            'deposit_status', 'payment_method', 'yookassa_payment_id',
            'refund_amount', 'refund_status',
            'created_at',
            'enquiry_id', 'msg_unread',
        ]

    def get_enquiry_id(self, obj):
        return getattr(obj, '_enquiry_id', None)

    def get_msg_unread(self, obj):
        return bool(getattr(obj, '_msg_unread', False))


class EnquiryCreateSerializer(serializers.ModelSerializer):
    """POST /api/v1/bookings/enquiries/  — private tour request or general message."""
    tour_slug      = serializers.SlugField(write_only=True)
    name           = serializers.CharField(required=False, allow_blank=True, max_length=120)
    email          = serializers.EmailField(required=False, allow_blank=True)
    preferred_from = serializers.DateField(required=False, allow_null=True)
    preferred_to   = serializers.DateField(required=False, allow_null=True)
    adults         = serializers.IntegerField(required=False, min_value=0, default=1)
    children       = serializers.IntegerField(required=False, min_value=0, default=0)
    infants        = serializers.IntegerField(required=False, min_value=0, default=0)
    message        = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model  = EnquiryMessage
        fields = [
            'tour_slug',
            'name', 'email',
            'preferred_from', 'preferred_to',
            'adults', 'children', 'infants',
            'message',
        ]

    def validate_tour_slug(self, value):
        from apps.tours.models import Tour
        try:
            return Tour.objects.get(slug=value)
        except Tour.DoesNotExist:
            raise serializers.ValidationError('Tour not found.')

    def create(self, validated_data):
        tour = validated_data.pop('tour_slug')
        user = self.context['request'].user
        return EnquiryMessage.objects.create(
            tour   = tour,
            sender = user if user.is_authenticated else None,
            **validated_data,
        )


class EnquiryReplySerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model  = EnquiryReply
        fields = ['id', 'sender_name', 'is_operator', 'body', 'created_at']

    def get_sender_name(self, obj):
        if obj.sender:
            name = (obj.sender.first_name + ' ' + obj.sender.last_name).strip()
            return name or obj.sender.email
        return 'Operator' if obj.is_operator else 'Guest'


class EnquiryDetailSerializer(serializers.ModelSerializer):
    tour_slug     = serializers.CharField(source='tour.slug',  read_only=True)
    tour_title    = serializers.CharField(source='tour.title', read_only=True)
    operator_name = serializers.SerializerMethodField()
    replies       = EnquiryReplySerializer(many=True, read_only=True)
    booking_ref   = serializers.SerializerMethodField()

    class Meta:
        model  = EnquiryMessage
        fields = [
            'id', 'tour_slug', 'tour_title', 'operator_name', 'name', 'email',
            'preferred_from', 'preferred_to',
            'adults', 'children', 'infants', 'message',
            'read_by_operator', 'operator_reply', 'replied_at', 'created_at',
            'replies', 'booking_ref',
        ]

    def get_operator_name(self, obj):
        op = obj.tour.operator
        name = (op.first_name + ' ' + op.last_name).strip()
        return name or op.email

    def get_booking_ref(self, obj):
        if not obj.sender:
            return None
        booking = obj.tour.bookings.filter(
            tourist=obj.sender,
            status__in=['pending', 'confirmed', 'completed'],
        ).order_by('-created_at').first()
        return booking.reference if booking else None
