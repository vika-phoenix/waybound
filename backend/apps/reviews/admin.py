"""
apps/reviews/admin.py — Task 20
"""
from django.contrib import admin
from django.utils import timezone
from .models import TourReview


@admin.register(TourReview)
class TourReviewAdmin(admin.ModelAdmin):
    list_display   = ['tourist', 'tour', 'rating', 'title', 'status',
                      'has_reply', 'created_at']
    list_filter    = ['status', 'rating', 'created_at']
    search_fields  = ['tourist__email', 'tour__slug', 'title', 'body']
    readonly_fields = ['created_at', 'updated_at', 'replied_at']
    list_editable  = ['status']
    ordering       = ['-created_at']
    actions        = ['approve_reviews', 'reject_reviews']

    fieldsets = (
        ('Review',    {'fields': ('tourist', 'tour', 'booking', 'rating', 'title', 'body', 'status')}),
        ('Reply',     {'fields': ('operator_reply', 'replied_at')}),
        ('Timestamps',{'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def has_reply(self, obj):
        return bool(obj.operator_reply)
    has_reply.boolean = True
    has_reply.short_description = 'Reply'

    def approve_reviews(self, request, queryset):
        for rev in queryset:
            rev.status = TourReview.Status.APPROVED
            rev.save()  # triggers _update_tour_stats
        self.message_user(request, f'{queryset.count()} review(s) approved.')
    approve_reviews.short_description = 'Approve selected reviews'

    def reject_reviews(self, request, queryset):
        for rev in queryset:
            rev.status = TourReview.Status.REJECTED
            rev.save()
        self.message_user(request, f'{queryset.count()} review(s) rejected.')
    reject_reviews.short_description = 'Reject selected reviews'
