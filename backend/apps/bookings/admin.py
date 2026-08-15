"""
apps/bookings/admin.py
"""
from django.contrib import admin
from django.db.models import Sum, Count
from django.urls import path, reverse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.html import format_html

from .models import Booking, EnquiryMessage


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display    = ['reference', 'tourist', 'tour', 'status', 'adults', 'children',
                       'total_price', 'currency', 'col_commission', 'col_payout',
                       'col_payout_status', 'departure_date', 'created_at']
    list_filter     = ['status', 'payout_status', 'currency', 'payment_method', 'created_at']
    search_fields   = ['reference', 'email', 'first_name', 'last_name',
                       'tour__slug', 'tourist__email', 'payout_reference']
    readonly_fields = ['reference', 'created_at', 'updated_at', 'confirmed_at', 'cancelled_at',
                       'col_collected', 'col_kept', 'col_commission', 'col_payout']
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
        ('Commission & payout', {
            'fields': ('col_collected', 'col_kept', 'commission_pct', 'col_commission',
                       'col_payout', 'payout_status', 'payout_sent_at', 'payout_reference'),
            'description': (
                'commission_pct is snapshotted when the first payment lands and should not '
                'normally be edited — changing it rewrites what this guide is owed. '
                'Commission is charged on what was kept, so a refunded booking owes nothing '
                'and a cancellation that kept a penalty is charged on the penalty.'
            ),
        }),
        ('Timestamps',  {'fields': ('created_at', 'updated_at', 'confirmed_at', 'cancelled_at'),
                          'classes': ('collapse',)}),
    )

    actions = ['confirm_bookings', 'mark_completed', 'mark_payout_sent']
    change_list_template = 'admin/bookings/booking/change_list.html'

    def changelist_view(self, request, extra_context=None):
        """Surface the payout count on the list itself — an admin should not
        have to go looking to find out someone is waiting to be paid."""
        extra_context = extra_context or {}
        extra_context['payouts_due_count'] = Booking.objects.filter(payout_status='due').count()
        return super().changelist_view(request, extra_context)

    # ── Money columns ────────────────────────────────────────────────────────

    @admin.display(description='Collected')
    def col_collected(self, obj):
        return f'{obj.amount_collected:.2f} {obj.currency}'

    @admin.display(description='Kept after refunds')
    def col_kept(self, obj):
        return f'{obj.amount_kept:.2f} {obj.currency}'

    @admin.display(description='Commission')
    def col_commission(self, obj):
        return f'{obj.commission_amount:.2f} ({obj.effective_commission_pct:g}%)'

    @admin.display(description='Guide is owed')
    def col_payout(self, obj):
        return f'{obj.payout_amount:.2f} {obj.currency}'

    @admin.display(description='Payout', ordering='payout_status')
    def col_payout_status(self, obj):
        colour = {'not_due': '#888', 'due': '#c0392b', 'paid': '#1a7a40'}[obj.payout_status]
        label  = obj.get_payout_status_display()
        if obj.payout_status == 'paid' and obj.payout_sent_at:
            label += f' {obj.payout_sent_at:%d %b}'
        return format_html('<b style="color:{}">{}</b>', colour, label)

    # ── Actions ──────────────────────────────────────────────────────────────

    def confirm_bookings(self, request, qs):
        updated = qs.filter(status='pending').update(
            status='confirmed', confirmed_at=timezone.now()
        )
        self.message_user(request, f'{updated} booking(s) confirmed.')
    confirm_bookings.short_description = '1. Confirm selected pending bookings'

    def mark_completed(self, request, qs):
        """
        Completing a trip is what makes the guide's share payable, so this has
        to move payout_status too — otherwise a manually completed booking
        never reaches the payouts list and the guide is silently never paid.
        """
        done = 0
        for bk in qs.filter(status='confirmed'):
            bk.status = Booking.Status.COMPLETED
            fields = ['status']
            if bk.payout_status == 'not_due' and bk.payout_amount > 0:
                bk.payout_status = 'due'
                fields.append('payout_status')
            bk.save(update_fields=fields)
            done += 1
        self.message_user(request, f'{done} booking(s) completed; payouts now due.')
    mark_completed.short_description = '2. Mark trips as completed (this is what makes a payout due)'

    def mark_payout_sent(self, request, qs):
        """
        Records that the bank transfer went out. One transfer usually covers
        several bookings, so the same reference is written to all of them —
        that is what makes "was I paid for VZ-ABC123?" answerable.
        """
        payable = qs.filter(payout_status='due')
        if 'apply' in request.POST:
            ref = (request.POST.get('payout_reference') or '').strip()
            now = timezone.now()
            n = payable.update(payout_status='paid', payout_sent_at=now, payout_reference=ref)
            self.message_user(request, f'{n} payout(s) marked sent under reference "{ref}".')
            return None
        return render(request, 'admin/bookings/mark_payout_sent.html', {
            **self.admin_site.each_context(request),
            'title': 'Record a payout',
            'bookings': payable.select_related('tour__operator'),
            'total_by_currency': _totals_by_currency(payable),
            'skipped': _why_not_payable(qs.exclude(payout_status='due')),
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        })
    mark_payout_sent.short_description = '3. Record that I paid the guide (asks for a transfer reference)'

    # ── "Who am I paying this week" ──────────────────────────────────────────

    def get_urls(self):
        return [
            path('payouts/', self.admin_site.admin_view(self.payouts_view),
                 name='bookings_booking_payouts'),
            path('payouts/record/<int:operator_id>/<str:currency>/',
                 self.admin_site.admin_view(self.payout_record_view),
                 name='bookings_booking_payout_record'),
        ] + super().get_urls()

    def payout_record_view(self, request, operator_id, currency):
        """
        Record one guide's transfer from the payouts page.

        The Action dropdown can do the same thing, but it is unlabelled, it
        sits among unrelated actions, and it appears to do nothing when the
        selection holds no payable booking. Arriving from "this guide is owed
        X" there is nothing to select and nothing to get wrong.
        """
        payable = (Booking.objects.filter(payout_status='due', currency=currency,
                                          tour__operator_id=operator_id)
                   .select_related('tour__operator'))
        if 'apply' in request.POST:
            ref = (request.POST.get('payout_reference') or '').strip()
            n = payable.update(payout_status='paid', payout_sent_at=timezone.now(),
                               payout_reference=ref)
            self.message_user(request, f'{n} payout(s) marked sent under reference "{ref}".')
            return redirect('admin:bookings_booking_payouts')
        return render(request, 'admin/bookings/mark_payout_sent.html', {
            **self.admin_site.each_context(request),
            'title': 'Record a payout',
            'bookings': payable,
            'total_by_currency': _totals_by_currency(payable),
            'skipped': [],
            'post_url': request.path,
        })

    def payouts_view(self, request):
        """
        The per-booking rows are the truth; this just groups them the way the
        money actually moves — one guide, one transfer.
        """
        due = (Booking.objects.filter(payout_status='due')
               .select_related('tour__operator').order_by('tour__operator__email'))
        groups = {}
        for bk in due:
            op = bk.tour.operator
            key = (op.pk, bk.currency)
            g = groups.setdefault(key, {
                'operator': op, 'currency': bk.currency, 'bookings': [],
                'owed': 0.0, 'commission': 0.0,
                'has_bank_details': bool(op.payout_account or op.payout_name),
                'record_url': reverse('admin:bookings_booking_payout_record',
                                      args=[op.pk, bk.currency]),
            })
            g['bookings'].append(bk)
            g['owed'] += bk.payout_amount
            g['commission'] += bk.commission_amount

        # Money already taken on trips that have not run yet. Without this the
        # page is blank until the first trip finishes, which reads as broken
        # rather than as "nothing is owed yet".
        upcoming = [b for b in Booking.objects.filter(payout_status='not_due')
                    .exclude(status=Booking.Status.CANCELLED)
                    .select_related('tour__operator') if b.payout_amount > 0]

        return render(request, 'admin/bookings/payouts.html', {
            **self.admin_site.each_context(request),
            'title': 'Payouts',
            'groups': sorted(groups.values(), key=lambda g: -g['owed']),
            'grand_total': _totals_by_currency(due),
            'upcoming': upcoming,
            'upcoming_total': _totals_by_currency(upcoming),
            'paid_recently': (Booking.objects.filter(payout_status='paid')
                              .select_related('tour__operator')
                              .order_by('-payout_sent_at')[:20]),
        })


def _why_not_payable(qs):
    """
    Turn "nothing happened" into a reason. A booking is skipped because the
    trip has not run, because no money was kept, or because it is already
    settled — and each needs a different next step from the admin.
    """
    out = []
    for bk in qs.select_related('tour'):
        if bk.payout_status == 'paid':
            when = bk.payout_sent_at.strftime('%d %b %Y') if bk.payout_sent_at else 'earlier'
            out.append((bk.reference, 'already paid on ' + when))
        elif bk.payout_amount <= 0:
            out.append((bk.reference, 'nothing was kept on this booking, so nothing is owed'))
        elif bk.status != Booking.Status.COMPLETED:
            out.append((bk.reference,
                        'the trip is not marked completed yet (status: %s)' % bk.get_status_display()))
        else:
            out.append((bk.reference, 'not marked due yet — run action 2 on it first'))
    return out


def _totals_by_currency(qs):
    out = {}
    for bk in qs:
        out.setdefault(bk.currency, {'owed': 0.0, 'commission': 0.0, 'count': 0})
        out[bk.currency]['owed'] += bk.payout_amount
        out[bk.currency]['commission'] += bk.commission_amount
        out[bk.currency]['count'] += 1
    return out


@admin.register(EnquiryMessage)
class EnquiryMessageAdmin(admin.ModelAdmin):
    list_display  = ['tour', 'name', 'email', 'adults', 'children',
                     'preferred_from', 'preferred_to', 'read_by_operator', 'created_at']
    list_filter   = ['read_by_operator', 'created_at']
    search_fields = ['email', 'name', 'tour__slug', 'sender__email']
    readonly_fields = ['created_at']
    list_editable   = ['read_by_operator']