"""
apps/bookings/admin.py  —  Task 18
"""
from django.contrib import admin
from django.utils import timezone
from .models import Booking, EnquiryMessage


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display    = ['reference', 'tourist', 'tour', 'status', 'adults', 'children',
                       'total_price', 'currency', 'departure_date', 'created_at']
    list_filter     = ['status', 'currency', 'payment_method', 'created_at']
    search_fields   = ['reference', 'email', 'first_name', 'last_name',
                       'tour__slug', 'tourist__email']
    readonly_fields = ['reference', 'created_at', 'updated_at', 'confirmed_at', 'cancelled_at']
    ordering        = ['-created_at']
    list_editable   = ['status']

    fieldsets = (
        ('Reference',   {'fields': ('reference', 'status', 'tour', 'departure', 'tourist')}),
        ('Travellers',  {'fields': ('adults', 'children', 'infants',
                                     'first_name', 'last_name', 'email', 'phone', 'country')}),
        ('Trip',        {'fields': ('departure_date', 'notes',
                                     'emergency_name', 'emergency_phone')}),
        ('Pricing',     {'fields': ('price_adult', 'price_child', 'total_price',
                                     'deposit_paid', 'currency')}),
        ('Payment',     {'fields': ('payment_method', 'yookassa_payment_id')}),
        ('Timestamps',  {'fields': ('created_at', 'updated_at', 'confirmed_at', 'cancelled_at'),
                          'classes': ('collapse',)}),
    )

    actions = ['confirm_bookings', 'mark_completed']

    def confirm_bookings(self, request, qs):
        updated = qs.filter(status='pending').update(
            status='confirmed', confirmed_at=timezone.now()
        )
        self.message_user(request, f'{updated} booking(s) confirmed.')
    confirm_bookings.short_description = 'Confirm selected pending bookings'

    def mark_completed(self, request, qs):
        updated = qs.filter(status='confirmed').update(status='completed')
        self.message_user(request, f'{updated} booking(s) marked completed.')
    mark_completed.short_description = 'Mark confirmed bookings as completed'


@admin.register(EnquiryMessage)
class EnquiryMessageAdmin(admin.ModelAdmin):
    list_display  = ['tour', 'name', 'email', 'adults', 'children',
                     'preferred_from', 'preferred_to', 'read_by_operator', 'created_at']
    list_filter   = ['read_by_operator', 'created_at']
    search_fields = ['email', 'name', 'tour__slug', 'sender__email']
    readonly_fields = ['created_at']
    list_editable   = ['read_by_operator']
