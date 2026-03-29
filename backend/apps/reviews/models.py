"""
apps/reviews/models.py — Task 20
TourReview: tourist submits a review after completing a tour.
"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class TourReview(models.Model):

    class Status(models.TextChoices):
        PENDING  = 'pending',  'Pending moderation'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    tour     = models.ForeignKey(
        'tours.Tour', on_delete=models.CASCADE, related_name='reviews'
    )
    booking  = models.ForeignKey(
        'bookings.Booking', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviews'
    )
    tourist  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='reviews'
    )

    rating  = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title   = models.CharField(max_length=200, blank=True)
    body    = models.TextField()

    # Operator reply
    operator_reply = models.TextField(blank=True)
    replied_at     = models.DateTimeField(null=True, blank=True)

    status     = models.CharField(
        max_length=10, choices=Status.choices, default=Status.APPROVED, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering       = ['-created_at']
        unique_together = [('tourist', 'tour')]   # one review per tourist per tour
        indexes = [
            models.Index(fields=['tour', 'status']),
        ]

    def __str__(self):
        return f'{self.tourist.email} → {self.tour.slug} ({self.rating}★)'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._update_tour_stats()

    def _update_tour_stats(self):
        """Recalculate tour.rating and tour.review_count from approved reviews."""
        from django.db.models import Avg, Count
        agg = TourReview.objects.filter(
            tour=self.tour, status=self.Status.APPROVED
        ).aggregate(avg=Avg('rating'), cnt=Count('id'))
        self.tour.rating       = agg['avg'] or 0
        self.tour.review_count = agg['cnt'] or 0
        self.tour.save(update_fields=['rating', 'review_count'])
