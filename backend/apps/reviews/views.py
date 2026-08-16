"""
apps/reviews/views.py

GET  /api/v1/reviews/            — public: approved reviews (filter by ?tour=<slug>)
POST /api/v1/reviews/            — tourist: submit review
GET  /api/v1/reviews/mine/       — tourist: own reviews
GET  /api/v1/reviews/operator/   — operator: reviews for own tours
PATCH /api/v1/reviews/<pk>/reply/ — operator: reply to a review
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import TourReview
from .serializers import TourReviewSerializer, TourReviewWriteSerializer

logger = logging.getLogger(__name__)


@api_view(['GET', 'POST'])
def review_list(request):
    """
    GET  — public list of approved reviews (filter by ?tour=<slug>)
    POST — tourist submits a new review
    """
    if request.method == 'GET':
        qs = TourReview.objects.filter(status=TourReview.Status.APPROVED).select_related('tourist', 'tour')
        tour_slug = request.GET.get('tour')
        if tour_slug:
            qs = qs.filter(tour__slug=tour_slug)
        serializer = TourReviewSerializer(qs, many=True, context={'request': request})
        return Response({'count': qs.count(), 'results': serializer.data})

    # POST — submit review (auth required)
    if not request.user.is_authenticated:
        return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

    serializer = TourReviewWriteSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    review = serializer.save()

    # Notify operator by email
    _notify_operator_new_review(review)

    return Response(TourReviewSerializer(review, context={'request': request}).data,
                    status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_reviews(request):
    """GET /api/v1/reviews/mine/  — tourist's own submitted reviews."""
    qs = TourReview.objects.filter(tourist=request.user).select_related('tour')
    serializer = TourReviewSerializer(qs, many=True, context={'request': request})
    return Response({'count': qs.count(), 'results': serializer.data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def operator_reviews(request):
    """GET /api/v1/reviews/operator/ — operator: reviews for own tours."""
    if request.user.role != 'operator' and not request.user.is_staff:
        return Response({'detail': 'Operator account required.'}, status=status.HTTP_403_FORBIDDEN)
    qs = TourReview.objects.filter(
        tour__operator=request.user
    ).select_related('tourist', 'tour').order_by('-created_at')
    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)
    serializer = TourReviewSerializer(qs, many=True, context={'request': request})
    return Response({'count': qs.count(), 'results': serializer.data})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def review_reply(request, pk):
    """PATCH /api/v1/reviews/<pk>/reply/ — operator adds/updates reply."""
    review = get_object_or_404(TourReview, pk=pk)
    if review.tour.operator != request.user and not request.user.is_staff:
        return Response({'detail': 'Not your tour.'}, status=status.HTTP_403_FORBIDDEN)
    reply = request.data.get('reply', '').strip()
    review.operator_reply = reply
    review.replied_at     = timezone.now() if reply else None
    review.save(update_fields=['operator_reply', 'replied_at'])
    return Response(TourReviewSerializer(review, context={'request': request}).data)


def _notify_operator_new_review(review):
    """Send email to operator when a new review is submitted for their tour."""
    try:
        from apps.mail import lang_for, send

        op = review.tour.operator
        site = getattr(settings, 'SITE_URL', 'http://127.0.0.1:5500')
        text = f'{review.title}\n\n{review.body}' if review.title else review.body
        send(op.email, 'operator_new_review', lang_for(op),
             url=f'{site}/operator-dashboard.html?tab=reviews',
             name=review.tourist.public_display_name,
             tour=review.tour.title,
             rating=review.rating,
             message=text)
    except Exception:
        logger.exception('Failed to send review notification email')
