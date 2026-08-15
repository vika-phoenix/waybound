"""
apps/tours/admin.py
"""
import logging

from django.contrib import admin, messages
from django.utils.html import format_html
from .models import Tour, DepartureDate, DayItinerary, StayBlock, CancelPeriod, TourPhoto, TourFAQ, SavedTour

logger = logging.getLogger(__name__)


class DepartureDateInline(admin.TabularInline):
    model  = DepartureDate
    extra  = 1
    fields = ['start_date', 'end_date', 'spots_total', 'spots_left', 'status', 'price_override']

class DayItineraryInline(admin.TabularInline):
    model  = DayItinerary
    extra  = 0
    fields = ['day_number', 'title', 'meals', 'elevation']

class StayBlockInline(admin.TabularInline):
    model  = StayBlock
    extra  = 0
    fields = ['property_name', 'property_type', 'comfort_level', 'night_from', 'night_to']

class CancelPeriodInline(admin.TabularInline):
    model  = CancelPeriod
    extra  = 0
    fields = ['days_before_min', 'days_before_max', 'penalty_pct', 'label']

class TourPhotoInline(admin.TabularInline):
    model           = TourPhoto
    extra           = 0
    fields          = ['image', 'order', 'caption', 'preview']
    readonly_fields = ['preview']

    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:50px;border-radius:4px">', obj.image.url)
        return '—'

class TourFAQInline(admin.TabularInline):
    model  = TourFAQ
    extra  = 0
    fields = ['order', 'question', 'answer']


@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    list_display    = ['title', 'operator', 'status', 'category', 'country',
                       'days', 'price_adult', 'rating', 'created_at']
    list_filter     = ['status', 'category', 'difficulty', 'tour_type', 'country']
    search_fields   = ['title', 'slug', 'destination', 'operator__email']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['created_at', 'updated_at', 'published_at', 'booking_count']
    list_editable   = ['status']
    ordering        = ['-created_at']
    inlines         = [DepartureDateInline, DayItineraryInline, StayBlockInline,
                       CancelPeriodInline, TourPhotoInline, TourFAQInline]

    fieldsets = (
        ('Identity',    {'fields': ('operator', 'title', 'slug', 'status', 'emoji')}),
        ('Classification', {'fields': ('category', 'categories', 'difficulty', 'tour_type')}),
        ('Geography',   {'fields': ('country', 'destination', 'region', 'latitude', 'longitude')}),
        ('Pricing',     {'fields': ('days', 'price_adult', 'price_child', 'currency', 'max_group', 'min_group')}),
        ('Content',     {'fields': ('description', 'highlights', 'includes', 'excludes',
                                     'requirements', 'meeting_point', 'end_point'), 'classes': ('collapse',)}),
        ('Extra info',  {'fields': ('language', 'min_age', 'max_age', 'is_private',
                                     'video_url', 'getting_there', 'organiser_note'), 'classes': ('collapse',)}),
        ('Stats',       {'fields': ('rating', 'review_count', 'booking_count'), 'classes': ('collapse',)}),
        ('Timestamps',  {'fields': ('created_at', 'updated_at', 'published_at'), 'classes': ('collapse',)}),
    )

    actions = ['publish_tours', 'pause_tours', 'reject_tours', 'delete_tours_safe']

    def publish_tours(self, request, queryset):
        """
        Publishing was a bare queryset.update(), so a tour went live and its
        guide was told nothing. Loop instead, and tell them.
        """
        from django.utils import timezone
        from .emails import notify_operator_tour_approved
        published, mailed = 0, 0
        for tour in queryset.select_related('operator'):
            tour.status = Tour.Status.LIVE
            tour.published_at = timezone.now()
            tour.save(update_fields=['status', 'published_at'])
            published += 1
            # A failed notice must never undo a publish that already happened.
            try:
                if notify_operator_tour_approved(tour):
                    mailed += 1
            except Exception as exc:
                logger.error('Tour-approved notice failed for %s: %s', tour.slug, exc)
        self.message_user(
            request, f'{published} tour(s) published; {mailed} guide(s) notified.')
    publish_tours.short_description = 'Publish selected tours (notifies the guide)'

    def pause_tours(self, request, queryset):
        queryset.update(status=Tour.Status.PAUSED)
    pause_tours.short_description = 'Pause selected tours'

    def reject_tours(self, request, queryset):
        """
        Ask for a reason before sending a tour back.

        A silent rejection tells the guide nothing: the tour reappears as a
        draft and they have no idea what to change, so they resubmit the same
        thing or give up. The reason goes straight into the email.
        """
        from django.shortcuts import render
        from .emails import notify_operator_tour_rejected

        if 'apply' in request.POST:
            reason = (request.POST.get('reason') or '').strip()
            sent = 0
            for tour in queryset.select_related('operator'):
                tour.status = Tour.Status.DRAFT
                tour.save(update_fields=['status'])
                try:
                    if notify_operator_tour_rejected(tour, reason):
                        sent += 1
                except Exception as exc:
                    logger.error('Tour-rejected notice failed for %s: %s', tour.slug, exc)
            self.message_user(
                request,
                f'{queryset.count()} tour(s) moved back to draft; {sent} guide(s) notified.')
            return None

        return render(request, 'admin/tours/reject_tours.html', {
            **self.admin_site.each_context(request),
            'title': 'Send tours back to the guide',
            'tours': queryset.select_related('operator'),
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        })
    reject_tours.short_description = 'Send back to draft (asks for a reason, notifies the guide)'

    def delete_tours_safe(self, request, queryset):
        from apps.bookings.models import Booking
        for tour in queryset:
            active = Booking.objects.filter(
                tour=tour, status__in=['pending', 'confirmed'],
            ).exists()
            if active:
                self.message_user(request,
                    f'Cannot delete "{tour.title}" — it has active bookings.', messages.ERROR)
            else:
                title = tour.title
                tour.delete()
                self.message_user(request, f'Deleted "{title}".', messages.SUCCESS)
    delete_tours_safe.short_description = 'Delete selected tours (only if no active bookings)'


@admin.register(SavedTour)
class SavedTourAdmin(admin.ModelAdmin):
    list_display  = ['tourist', 'tour', 'created_at']
    search_fields = ['tourist__email', 'tour__slug']
