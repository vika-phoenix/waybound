"""
apps/tours/views.py  —  Task 18

Endpoints:
  GET  /api/v1/tours/                   — public list (filtered, paginated)
  GET  /api/v1/tours/<slug>/            — public detail
  POST /api/v1/tours/                   — operator create
  PATCH /api/v1/tours/<slug>/           — operator edit (own tours only)
  DELETE /api/v1/tours/<slug>/          — operator soft-delete (→ archived)

  GET    /api/v1/tours/saved/           — tourist: list saved tours
  POST   /api/v1/tours/<slug>/save/     — tourist: save tour
  DELETE /api/v1/tours/<slug>/save/     — tourist: unsave tour

  POST   /api/v1/tours/<slug>/photos/   — operator: upload photos (multipart)
  DELETE /api/v1/tours/<slug>/photos/<photo_id>/  — operator: delete photo

  GET    /api/v1/tours/operator/        — operator: own tour list (dashboard)
"""
import django_filters
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Tour, TourPhoto, SavedTour, StayBlock, PropertyPhoto, WaitlistEntry
from .serializers import (
    TourListSerializer,
    TourDetailSerializer,
    TourWriteSerializer,
    TourPhotoSerializer,
    PropertyPhotoSerializer,
    SavedTourSerializer,
    OperatorTourListSerializer,
    WaitlistEntrySerializer,
)
from .permissions import IsOperatorOwner, IsOperator


# ── Filters ───────────────────────────────────────────────────────────────────

class TourFilter(django_filters.FilterSet):
    category    = django_filters.CharFilter(method='filter_category')

    def filter_category(self, queryset, name, value):
        """Support ?category=Trekking,Wildlife comma-separated."""
        cats = [c.strip() for c in value.split(',') if c.strip()]
        if not cats:
            return queryset
        from django.db.models import Q
        q = Q()
        for cat in cats:
            q |= Q(category__iexact=cat) | Q(categories__icontains=cat)
        return queryset.filter(q)
    country     = django_filters.CharFilter(lookup_expr='icontains')
    destination = django_filters.CharFilter(lookup_expr='icontains')
    min_price   = django_filters.NumberFilter(field_name='price_adult', lookup_expr='gte')
    max_price   = django_filters.NumberFilter(field_name='price_adult', lookup_expr='lte')
    min_days    = django_filters.NumberFilter(field_name='days', lookup_expr='gte')
    max_days    = django_filters.NumberFilter(field_name='days', lookup_expr='lte')
    difficulty  = django_filters.CharFilter(lookup_expr='iexact')
    tour_type   = django_filters.CharFilter(lookup_expr='iexact')

    class Meta:
        model  = Tour
        fields = ['category', 'country', 'destination', 'difficulty', 'tour_type']


# ── Public endpoints ──────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
def tour_list(request):
    """
    GET  — public tour listing with filters
    POST — operator creates a new tour (requires operator role)
    """
    if request.method == 'GET':
        qs = Tour.objects.filter(status=Tour.Status.LIVE, is_private=False).select_related('operator').prefetch_related(
            'photos', 'departures'
        )
        # Apply filters manually (django-filter works better in ViewSets but we keep
        # function-based views for consistency with the rest of the codebase)
        f = TourFilter(request.GET, queryset=qs)
        qs = f.qs

        # Search
        q = request.GET.get('q', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(destination__icontains=q) |
                Q(country__icontains=q) |
                Q(description__icontains=q)
            )

        # Ordering
        order = request.GET.get('order', '-created_at')
        allowed = ['price_adult', '-price_adult', 'days', '-days', 'rating', '-rating', '-created_at']
        if order in allowed:
            qs = qs.order_by(order)

        # Pagination
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        paginator.page_size = int(request.GET.get('page_size', 20))
        page = paginator.paginate_queryset(qs, request)
        serializer = TourListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    # POST — create
    if not request.user.is_authenticated or request.user.role != 'operator':
        return Response({'detail': 'Operator account required.'}, status=status.HTTP_403_FORBIDDEN)

    serializer = TourWriteSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    tour = serializer.save()
    return Response(TourDetailSerializer(tour, context={'request': request}).data,
                    status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
def tour_detail(request, slug):
    """
    GET    — public detail
    PATCH  — operator edit (own tour only)
    DELETE — operator soft-delete (→ archived)
    """
    if request.method == 'GET':
        qs = Tour.objects.select_related('operator').prefetch_related(
            'photos', 'departures', 'itinerary', 'stays', 'cancel_policy', 'faqs'
        )
        # Operators and admins can preview their own tours at any status
        if request.user.is_authenticated:
            tour = qs.filter(slug=slug).first()
            if tour and (tour.status == Tour.Status.LIVE
                         or tour.operator == request.user
                         or request.user.is_staff):
                return Response(TourDetailSerializer(tour, context={'request': request}).data)
        tour = get_object_or_404(qs, slug=slug, status=Tour.Status.LIVE)
        return Response(TourDetailSerializer(tour, context={'request': request}).data)

    # Write operations require auth + ownership
    tour = get_object_or_404(Tour, slug=slug)
    if not request.user.is_authenticated:
        return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
    if tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'You do not own this tour.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'PATCH':
        # If the tour is under review, editing resets it to draft so it goes
        # through the review process again.
        if tour.status == Tour.Status.REVIEW:
            tour.status = Tour.Status.DRAFT
            tour.save(update_fields=['status'])

        # Snapshot material values BEFORE the update so we can detect changes.
        from apps.bookings.models import Booking
        from .emails import MATERIAL_FIELDS, notify_tourists_of_tour_change, notify_admin_of_tour_change

        has_active_bookings = Booking.objects.filter(
            tour=tour,
            status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
        ).exists()

        pre_snapshot: dict = {}
        if has_active_bookings:
            pre_snapshot = {
                'price_adult':   str(tour.price_adult),
                'price_child':   str(tour.price_child),
                'cancel_policy': sorted(
                    [{'min': cp.days_before_min, 'max': cp.days_before_max, 'pct': cp.penalty_pct}
                     for cp in tour.cancel_policy.all()],
                    key=lambda x: x['min']
                ),
                'extras':        tour.extras,
                'stays':         [{'room_types': s.room_types} for s in tour.stays.all()],
                'meeting_point': tour.meeting_point or '',
                'meeting_time':  tour.meeting_time or '',
                'destination':   tour.destination or '',
            }

        serializer = TourWriteSerializer(tour, data=request.data, partial=True,
                                          context={'request': request})
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()

        # Detect which material fields changed and notify tourists.
        if has_active_bookings and pre_snapshot:
            changed = []
            if str(updated.price_adult) != pre_snapshot['price_adult']:
                changed.append('price_adult')
            if str(updated.price_child) != pre_snapshot['price_child']:
                changed.append('price_child')
            post_policy = sorted(
                [{'min': cp.days_before_min, 'max': cp.days_before_max, 'pct': cp.penalty_pct}
                 for cp in updated.cancel_policy.all()],
                key=lambda x: x['min']
            )
            if post_policy != pre_snapshot['cancel_policy']:
                changed.append('cancel_policy')
            if updated.extras != pre_snapshot['extras']:
                changed.append('extras')
            post_stays = [{'room_types': s.room_types} for s in updated.stays.all()]
            if post_stays != pre_snapshot['stays']:
                changed.append('stays')
            if (updated.meeting_point or '') != pre_snapshot['meeting_point']:
                changed.append('meeting_point')
            if (updated.meeting_time or '') != pre_snapshot['meeting_time']:
                changed.append('meeting_time')
            if (updated.destination or '') != pre_snapshot['destination']:
                changed.append('destination')

            if changed:
                notify_tourists_of_tour_change(updated, changed)
                notify_admin_of_tour_change(updated, changed)

        return Response(TourDetailSerializer(updated, context={'request': request}).data)

    if request.method == 'DELETE':
        from apps.bookings.models import Booking
        # Block archiving if any active (pending/confirmed) bookings exist
        active = Booking.objects.filter(
            tour=tour,
            status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
        ).exists()
        if active:
            return Response(
                {'detail': 'This tour has active bookings. Resolve all bookings before archiving.'},
                status=status.HTTP_409_CONFLICT,
            )
        # Always archive — never hard delete (preserves booking history & reviews)
        tour.status = Tour.Status.ARCHIVED
        tour.save(update_fields=['status'])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Saved tours ───────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def saved_tour_list(request):
    """GET /api/v1/tours/saved/"""
    saved = SavedTour.objects.filter(tourist=request.user).select_related('tour__operator').prefetch_related(
        'tour__photos'
    )
    serializer = SavedTourSerializer(saved, many=True, context={'request': request})
    return Response({'count': saved.count(), 'results': serializer.data})


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def saved_tour_toggle(request, slug):
    """
    POST   /api/v1/tours/<slug>/save/  — save tour (201 created, 200 already saved)
    DELETE /api/v1/tours/<slug>/save/  — unsave tour
    """
    tour = get_object_or_404(Tour, slug=slug)

    if request.method == 'POST':
        _, created = SavedTour.objects.get_or_create(tourist=request.user, tour=tour)
        return Response({'saved': True}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    SavedTour.objects.filter(tourist=request.user, tour=tour).delete()
    return Response({'saved': False}, status=status.HTTP_204_NO_CONTENT)


# ── Waitlist endpoint ─────────────────────────────────────────────────────────

@api_view(['POST'])
def waitlist_join(request, slug):
    """
    POST /api/v1/tours/<slug>/waitlist/  — no auth required
    Body: { "email": "...", "name": "...", "departure_label": "...", "departure_id": <int> }
    Returns 201 if added, 200 if already on list.
    """
    from .models import DepartureDate
    from .emails import send_waitlist_confirmation

    tour = get_object_or_404(Tour, slug=slug)
    serializer = WaitlistEntrySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    departure_id = request.data.get('departure_id')
    departure    = None
    if departure_id:
        departure = DepartureDate.objects.filter(id=departure_id, tour=tour).first()

    name          = serializer.validated_data.get('name', '').strip()
    dep_label     = serializer.validated_data.get('departure_label', '')
    # Fall back label to start_date string so notify_waitlist_for_departure can match it
    if not dep_label and departure:
        dep_label = str(departure.start_date)

    entry, created = WaitlistEntry.objects.get_or_create(
        tour=tour,
        email=serializer.validated_data['email'],
        departure_label=dep_label,
        defaults={'name': name, 'departure': departure},
    )
    if not created and name and not entry.name:
        entry.name = name
        entry.save(update_fields=['name'])

    if created:
        send_waitlist_confirmation(tour, entry, departure)
        try:
            from .telegram import notify_operator_waitlist_entry
            notify_operator_waitlist_entry(tour, entry, departure)
        except Exception:
            pass

    return Response(
        {'on_waitlist': True},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# ── Photo upload ──────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def tour_photo_upload(request, slug):
    """
    POST /api/v1/tours/<slug>/photos/
    Body: multipart — file=<image>, order=<int> (optional), caption=<str> (optional)
    """
    tour = get_object_or_404(Tour, slug=slug)
    if tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your tour.'}, status=status.HTTP_403_FORBIDDEN)

    file = request.FILES.get('file')
    if not file:
        return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

    order   = int(request.data.get('order', tour.photos.count()))
    caption = request.data.get('caption', '')

    photo = TourPhoto.objects.create(tour=tour, image=file, order=order, caption=caption)
    return Response(TourPhotoSerializer(photo, context={'request': request}).data,
                    status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def tour_photo_delete(request, slug, photo_id):
    """DELETE /api/v1/tours/<slug>/photos/<photo_id>/"""
    tour  = get_object_or_404(Tour, slug=slug)
    photo = get_object_or_404(TourPhoto, id=photo_id, tour=tour)

    if tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your tour.'}, status=status.HTTP_403_FORBIDDEN)

    photo.image.delete(save=False)
    photo.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Operator dashboard ────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def operator_tour_list(request):
    """
    GET /api/v1/tours/operator/
    Returns the authenticated operator's own tours (all statuses).
    """
    if request.user.role != 'operator' and not request.user.is_staff:
        return Response({'detail': 'Operator account required.'}, status=status.HTTP_403_FORBIDDEN)

    qs = Tour.objects.filter(operator=request.user).prefetch_related('photos', 'departures')

    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    serializer = OperatorTourListSerializer(qs, many=True, context={'request': request})
    return Response({'count': qs.count(), 'results': serializer.data})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def tour_publish(request, slug):
    """
    PATCH /api/v1/tours/<slug>/publish/
    Operator submits tour for review (draft → review) or admin publishes (review → live).
    """
    tour = get_object_or_404(Tour, slug=slug)
    if tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your tour.'}, status=status.HTTP_403_FORBIDDEN)

    if request.user.is_staff:
        # Admin approves
        tour.status = Tour.Status.LIVE
        tour.published_at = timezone.now()
    else:
        # Operator must be verified before submitting
        if not request.user.is_verified:
            return Response(
                {'detail': 'Your account must be verified before you can submit tours for review. '
                           'Please upload your ID document from your settings page.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Operator submits for review
        if tour.status not in [Tour.Status.DRAFT, Tour.Status.PAUSED]:
            return Response({'detail': f'Cannot submit from status: {tour.status}'},
                            status=status.HTTP_400_BAD_REQUEST)
        tour.status = Tour.Status.REVIEW

    tour.save(update_fields=['status', 'published_at'])
    return Response({'status': tour.status})


# ── Property (stay) photo upload ───────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def stay_photo_upload(request, slug, night_from):
    """
    POST /api/v1/tours/<slug>/stays/<night_from>/photos/
    Uploads a photo for the StayBlock covering that night.
    """
    tour = get_object_or_404(Tour, slug=slug)
    if tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your tour.'}, status=status.HTTP_403_FORBIDDEN)

    stay = get_object_or_404(StayBlock, tour=tour, night_from=night_from)

    file = request.FILES.get('file')
    if not file:
        return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

    order   = int(request.data.get('order', stay.photos.count()))
    caption = request.data.get('caption', '')

    photo = PropertyPhoto.objects.create(stay=stay, image=file, order=order, caption=caption)
    return Response(PropertyPhotoSerializer(photo, context={'request': request}).data,
                    status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def stay_photo_delete(request, slug, photo_id):
    """DELETE /api/v1/tours/<slug>/stays/photos/<photo_id>/"""
    tour  = get_object_or_404(Tour, slug=slug)
    photo = get_object_or_404(PropertyPhoto, id=photo_id, stay__tour=tour)

    if tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your tour.'}, status=status.HTTP_403_FORBIDDEN)

    photo.image.delete(save=False)
    photo.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
