"""
apps/bookings/admin_forms.py

Booking someone in by hand.

Not every traveller can pay through the site. Some cannot use a card at all,
some are in a country neither rail reaches, and some simply write to us instead
of to the guide. Until now the only answer was to tell them to try again, which
in practice sends the trip off the platform: the guide can take the money
directly, and then there is no record, no commission, and no cover for either
side if the trip goes wrong.

The money still comes to us. Nothing about how a booking behaves afterwards
changes — the guide is paid the same net, the commission is the same, the
cancellation terms are the same. The only difference is that a person, not a
webhook, recorded that it arrived.
"""
from django import forms
from django.utils import timezone

from apps.tours.models import Tour, DepartureDate
from .models import Booking


class ManualBookingForm(forms.Form):
    tour = forms.ModelChoiceField(
        queryset=Tour.objects.none(),
        help_text='Only live and paused tours can be booked into.',
    )
    departure = forms.ModelChoiceField(
        queryset=DepartureDate.objects.none(), required=False,
        help_text='Leave blank for a tour with no fixed dates. Seats come off '
                  'the departure exactly as they would for an online booking.',
    )

    first_name = forms.CharField(max_length=60)
    last_name  = forms.CharField(max_length=60)
    email      = forms.EmailField(
        help_text='If this address already has an account, the booking is '
                  'attached to it and appears in their My bookings.')
    phone      = forms.CharField(max_length=20, required=False)
    country    = forms.CharField(max_length=80, required=False)

    adults   = forms.IntegerField(min_value=1, initial=1)
    children = forms.IntegerField(min_value=0, initial=0, required=False)
    infants  = forms.IntegerField(min_value=0, initial=0, required=False)

    amount_received = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=0,
        help_text='What has actually landed in our account, in the tour currency. '
                  'Enter 0 to hold the booking before the money arrives.')
    how_paid = forms.CharField(
        max_length=200, required=False, label='How it arrived',
        help_text='Bank reference, transfer date, "cash at the office" — whatever '
                  'lets you match this against a statement later.')
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)

    notify = forms.BooleanField(
        required=False, initial=True, label='Email the traveller and the guide',
        help_text='The guide needs to know a seat has gone. The traveller needs '
                  'a reference and something to show at the meeting point.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tour'].queryset = (
            Tour.objects.filter(status__in=[Tour.Status.LIVE, Tour.Status.PAUSED])
            .select_related('operator').order_by('title'))
        self.fields['departure'].queryset = (
            DepartureDate.objects.filter(start_date__gte=timezone.now().date())
            .exclude(status=DepartureDate.Status.CANCELLED)
            .select_related('tour').order_by('tour__title', 'start_date'))

    def clean(self):
        data  = super().clean()
        tour  = data.get('tour')
        dep   = data.get('departure')
        party = (data.get('adults') or 0) + (data.get('children') or 0)

        if tour and party > tour.max_group:
            raise forms.ValidationError(
                f'{party} travellers exceeds this tour\'s maximum group of {tour.max_group}.')

        if dep:
            if tour and dep.tour_id != tour.pk:
                raise forms.ValidationError(
                    f'That departure belongs to "{dep.tour.title}", not "{tour.title}".')
            if dep.spots_left < party:
                # Overbooking by hand is the one mistake this form could make
                # that the online path cannot, so it is refused rather than
                # warned about.
                raise forms.ValidationError(
                    f'Only {dep.spots_left} seat(s) left on that departure — '
                    f'not enough for {party}.')
        return data

    # ── Creating the booking ────────────────────────────────────────────────

    def save(self):
        """Create the booking, take the seats, and snapshot the commission."""
        from django.contrib.auth import get_user_model
        from apps.bookings.views import PLATFORM_DEFAULT_CANCEL_POLICY

        d        = self.cleaned_data
        tour     = d['tour']
        dep      = d.get('departure')
        adults   = d['adults']
        children = d.get('children') or 0
        infants  = d.get('infants') or 0
        amount   = d['amount_received']

        price_adult = float(tour.price_adult)
        price_child = float(tour.price_child_effective)
        total = (adults * price_adult) + (children * price_child)

        # Same snapshot the online path takes: the terms a traveller agreed to
        # must not move when the guide later edits the policy.
        policy = [
            {'days_before_min': cp.days_before_min,
             'days_before_max': cp.days_before_max,
             'penalty_pct':     cp.penalty_pct,
             'label':           cp.label}
            for cp in tour.cancel_policy.all()
        ] or PLATFORM_DEFAULT_CANCEL_POLICY

        User = get_user_model()
        tourist = User.objects.filter(email__iexact=d['email']).first()

        note_bits = []
        if d.get('how_paid'):
            note_bits.append('Paid offline: ' + d['how_paid'])
        if d.get('notes'):
            note_bits.append(d['notes'])

        paid = amount > 0
        booking = Booking.objects.create(
            tourist        = tourist,
            tour           = tour,
            departure      = dep,
            departure_date = dep.start_date if dep else None,
            adults=adults, children=children, infants=infants,
            first_name = d['first_name'], last_name = d['last_name'],
            email      = d['email'],
            phone      = d.get('phone') or '', country = d.get('country') or '',
            notes      = '\n\n'.join(note_bits),
            price_adult = price_adult, price_child = price_child,
            total_price = total, currency = tour.currency,
            cancel_policy_snapshot = policy,
            payment_method = 'bank',
            deposit_paid   = amount,
            deposit_status = 'paid' if paid else 'pending',
            status      = Booking.Status.CONFIRMED if paid else Booking.Status.PENDING,
            confirmed_at = timezone.now() if paid else None,
        )

        # Commission is snapshotted the moment money is recognised, exactly as
        # the webhooks do it — otherwise a later rate change would silently
        # rewrite what this guide is owed.
        if paid:
            booking.snapshot_commission()
            if dep:
                dep.spots_left = max(0, dep.spots_left - (adults + children))
                dep.save(update_fields=['spots_left'])

        return booking
