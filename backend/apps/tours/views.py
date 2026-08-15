"""
apps/tours/views.py

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
import logging

from django.utils import timezone
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)

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
        # Operators, admins, and tourists with a booking can view at any status
        if request.user.is_authenticated:
            tour = qs.filter(slug=slug).first()
            if tour:
                from apps.bookings.models import Booking
                has_booking = Booking.objects.filter(
                    tourist=request.user, tour=tour
                ).exclude(status=Booking.Status.CANCELLED).exists()
                if (tour.status == Tour.Status.LIVE
                        or tour.operator == request.user
                        or request.user.is_staff
                        or has_booking):
                    return Response(TourDetailSerializer(tour, context={'request': request}).data)
        tour = get_object_or_404(qs, slug=slug, status=Tour.Status.LIVE, is_private=False)
        return Response(TourDetailSerializer(tour, context={'request': request}).data)

    # Write operations require auth + ownership
    tour = get_object_or_404(Tour, slug=slug)
    if not request.user.is_authenticated:
        return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
    if tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'You do not own this tour.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'PATCH':
        # Status-only PATCH: pause ↔ unpause (serializer doesn't expose status field)
        # `confirm` rides along on the same request — see the pause guard below.
        if 'status' in request.data and set(request.data.keys()) <= {'status', 'confirm'}:
            new_status = request.data['status']
            OPERATOR_STATUS_TRANSITIONS = {
                'paused': (Tour.Status.LIVE,   Tour.Status.PAUSED),
                'live':   (Tour.Status.PAUSED, Tour.Status.LIVE),
            }
            if new_status not in OPERATOR_STATUS_TRANSITIONS:
                return Response({'detail': 'Invalid status transition.'}, status=status.HTTP_400_BAD_REQUEST)
            required_current, target = OPERATOR_STATUS_TRANSITIONS[new_status]
            if tour.status != required_current:
                return Response(
                    {'detail': f'Tour must be {required_current} to change to {new_status}.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Pausing only delists the tour — every booking already taken still
            # has to run. Guides read "paused" as "off", so name the people who
            # are still owed a trip before the switch flips.
            #
            # Archive refuses outright (409, no way through); pause only asks,
            # because pausing a tour you are still running is legitimate — it
            # stops new bookings without stranding the travellers already on it.
            # To actually call the trip off, cancel the departure instead.
            if target == Tour.Status.PAUSED and not request.data.get('confirm'):
                from apps.bookings.models import Booking
                active = list(Booking.objects.filter(
                    tour=tour,
                    status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
                ).only('adults', 'children', 'departure_date'))
                if active:
                    dated = sorted(b.departure_date for b in active if b.departure_date)
                    return Response({
                        'detail': 'This tour has active bookings. Pausing hides it from '
                                  'travellers and stops new bookings, but it does not '
                                  'cancel the trips already booked — you still have to '
                                  'run them.',
                        'requires_confirmation': True,
                        'active_bookings': len(active),
                        'travellers': sum((b.adults or 0) + (b.children or 0) for b in active),
                        'next_departure': str(dated[0]) if dated else None,
                    }, status=status.HTTP_409_CONFLICT)

            tour.status = target
            tour.save(update_fields=['status'])
            return Response(TourDetailSerializer(tour, context={'request': request}).data)

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
    try:
        photo.make_thumbnail()  # small fast version for cards/gallery grid
    except Exception:
        pass  # never fail the upload over a thumbnail
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

    # Both directions need a notice, and neither may fail the transition that
    # already happened: an admin who approves a tour must not see an error
    # because a mail server was down.
    if tour.status == Tour.Status.REVIEW:
        # Only an admin can move review -> live, so a submission nobody is told
        # about sits invisible until someone opens the admin by chance.
        try:
            from .emails import notify_admin_tour_submitted
            notify_admin_tour_submitted(tour)
        except Exception as exc:
            logger.error('Tour-submitted notice failed for %s: %s', tour.slug, exc)
    elif tour.status == Tour.Status.LIVE:
        try:
            from .emails import notify_operator_tour_approved
            notify_operator_tour_approved(tour)
        except Exception as exc:
            logger.error('Tour-approved notice failed for %s: %s', tour.slug, exc)

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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def departure_cancel(request, slug, dep_id):
    """
    POST /api/v1/tours/<slug>/departures/<dep_id>/cancel/
    Body: { reason?: str, confirm: true }

    The trip is not running. Cancels the departure and every live booking on
    it, refunding each in full.

    Without this a guide cancels bookings one at a time: eight travellers means
    eight operations, eight refunds and eight emails that never say they are
    the same event — and if one is missed, that person still turns up.

    Refunds use the operator path, so travellers get 100% back regardless of
    how close to departure it is. A trip the guide cancelled is never the
    traveller's fault.

    Partial failures do not abort. A refund that a provider rejects is flagged
    for a human, but the booking is still cancelled and the traveller still
    told — leaving someone believing their trip is on is far worse than a
    refund that needs chasing.
    """
    from apps.bookings.models import Booking
    from apps.bookings.views import _compute_refund, _issue_refund
    from .models import DepartureDate

    tour = get_object_or_404(Tour, slug=slug)
    if tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your tour.'}, status=status.HTTP_403_FORBIDDEN)

    dep = get_object_or_404(DepartureDate, pk=dep_id, tour=tour)
    if dep.status == DepartureDate.Status.CANCELLED:
        return Response({'detail': 'This departure is already cancelled.'},
                        status=status.HTTP_400_BAD_REQUEST)

    live = list(Booking.objects.filter(
        departure=dep,
        status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
    ).select_related('tour'))

    # Preview so the UI can say "this cancels 3 bookings and refunds $5,240"
    # before anyone commits to it.
    if not request.data.get('confirm'):
        total = sum(float(b.deposit_paid) + float(b.balance_paid) for b in live)
        return Response({
            'preview': True,
            'departure': str(dep.start_date),
            'bookings_affected': len(live),
            'travellers': sum((b.adults or 0) + (b.children or 0) for b in live),
            'refund_total': round(total, 2),
            'currency': tour.currency,
        })

    reason = (request.data.get('reason') or '').strip()

    dep.status = DepartureDate.Status.CANCELLED
    dep.save(update_fields=['status'])

    cancelled, refunded, manual = 0, 0, []
    for b in live:
        try:
            amount, _pct, _tier = _compute_refund(b, 'operator')
            b.status = Booking.Status.CANCELLED
            b.cancelled_at = timezone.now()
            if amount > 0:
                b.refund_amount = amount
                ok, msg = _issue_refund(b, amount)
                if ok:
                    b.refund_status = 'issued'
                    refunded += 1
                else:
                    b.refund_status = 'manual' if msg == 'bank' else 'pending'
                    manual.append(b.reference)
            else:
                b.refund_status = 'none'
            b.save(update_fields=['status', 'cancelled_at',
                                  'refund_amount', 'refund_status'])
            cancelled += 1
            _email_departure_cancelled(b, reason)
        except Exception as exc:
            # Keep going: one bad booking must not strand the rest.
            logger.error('Departure cancel failed for booking %s: %s',
                         getattr(b, 'reference', '?'), exc)

    logger.info('Departure %s of %s cancelled: %d bookings, %d auto-refunded',
                dep.start_date, tour.slug, cancelled, refunded)

    return Response({
        'departure': str(dep.start_date),
        'cancelled_bookings': cancelled,
        'auto_refunded': refunded,
        'needs_manual_refund': manual,
    })


def _email_departure_cancelled(booking, reason):
    """One clear message: the trip is off, here is your money back."""
    from django.core.mail import send_mail
    from django.conf import settings as _s

    to = booking.email or (booking.tourist.email if booking.tourist else '')
    if not to:
        return
    why = f'\n\nReason given: {reason}' if reason else ''
    try:
        send_mail(
            f'Cancelled: {booking.tour.title} on {booking.departure_date}',
            (f'We are sorry — the {booking.departure_date} departure of '
             f'"{booking.tour.title}" has been cancelled by the guide.{why}\n\n'
             f'You are being refunded in full: '
             f'{booking.currency} {booking.refund_amount}.\n'
             f'Booking reference: {booking.reference}\n\n'
             f'Refunds normally reach your account within 5-10 working days. '
             f'You do not need to do anything.\n\n'
             f'{getattr(_s, "FRONTEND_URL", "")}/adventures.html\n'),
            getattr(_s, 'DEFAULT_FROM_EMAIL', 'noreply@kavkazland.com'),
            [to], fail_silently=True,
        )
    except Exception as exc:
        logger.error('Cancellation email failed for %s: %s', booking.reference, exc)
