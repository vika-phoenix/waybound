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
        from apps.bookings.views import _html_email
        op = review.tour.operator
        tourist_name = ((review.tourist.first_name or '') + ' ' + (review.tourist.last_name or '')).strip() or review.tourist.email
        stars = '\u2605' * review.rating + '\u2606' * (5 - review.rating)
        site = getattr(settings, 'SITE_URL', 'http://127.0.0.1:5500')
        from_em = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@waybound.com')

        body = (
            f'<p style="margin:0 0 14px;font-size:14px;color:#0d1f2d;line-height:1.65">'
            f'<strong>{tourist_name}</strong> left a <strong>{stars} ({review.rating}/5)</strong> '
            f'review for <strong>{review.tour.title}</strong>.</p>'
        )
        if review.title:
            body += f'<p style="margin:0 0 8px;font-size:14px;font-weight:600;color:#0d1f2d">{review.title}</p>'
        body += f'<p style="margin:0 0 14px;font-size:14px;color:#4a5568;line-height:1.65">{review.body}</p>'

        send_mail(
            subject=f'New review for {review.tour.title}: {review.rating}/5 stars',
            message=f'{tourist_name} left a {review.rating}/5 review for "{review.tour.title}".\n\n{review.body}',
            from_email=from_em,
            html_message=_html_email(
                f'New review: {review.tour.title}',
                body,
                'View in dashboard',
                f'{site}/operator-dashboard.html?tab=reviews',
            ),
            recipient_list=[op.email],
            fail_silently=True,
        )
    except Exception:
        logger.exception('Failed to send review notification email')
