"""
apps/bookings/models.py
Booking and enquiry models.

A Booking is created when a tourist submits the booking form.
Status flow:  pending → confirmed → completed  (or → cancelled)

EnquiryMessage handles tour enquiries. Reply threading is supported
via EnquiryReply (tourist and operator can exchange follow-up messages).
"""
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
import uuid


def booking_ref():
    """Short human-readable reference: VZ-XXXXXX"""
    return 'VZ-' + uuid.uuid4().hex[:6].upper()


class Booking(models.Model):

    class Status(models.TextChoices):
        PENDING    = 'pending',    'Pending payment'
        CONFIRMED  = 'confirmed',  'Confirmed'
        COMPLETED  = 'completed',  'Completed'
        CANCELLED  = 'cancelled',  'Cancelled'
        REFUNDED   = 'refunded',   'Refunded'

    # ── Core relations ─────────────────────────────────────
    tourist         = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,          # allow guest bookings
        related_name='bookings',
    )
    tour            = models.ForeignKey(
        'tours.Tour',
        on_delete=models.PROTECT,
        related_name='bookings',
    )
    departure       = models.ForeignKey(
        'tours.DepartureDate',
        on_delete=models.SET_NULL,
        null=True, blank=True,           # null for single-day tours
        related_name='bookings',
    )

    # ── Reference ──────────────────────────────────────────
    reference       = models.CharField(max_length=12, unique=True, default=booking_ref, editable=False)

    # ── Status ─────────────────────────────────────────────
    status          = models.CharField(max_length=12, choices=Status.choices,
                                        default=Status.PENDING, db_index=True)

    # ── Guest counts ───────────────────────────────────────
    adults          = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    children        = models.PositiveSmallIntegerField(default=0)
    infants         = models.PositiveSmallIntegerField(default=0)

    @property
    def guests(self):
        return self.adults + self.children + self.infants

    # ── Traveller details ──────────────────────────────────
    first_name      = models.CharField(max_length=60)
    last_name       = models.CharField(max_length=60)
    email           = models.EmailField()
    phone           = models.CharField(max_length=20)
    country         = models.CharField(max_length=80, blank=True)
    emergency_name  = models.CharField(max_length=120, blank=True)
    emergency_phone = models.CharField(max_length=20, blank=True)
    notes           = models.TextField(blank=True)
    room_preference = models.CharField(max_length=120, blank=True,
                                        help_text='Room type selected at booking time')
    selected_extras = models.TextField(blank=True,
                                        help_text='Comma-separated extra services selected at booking time')
    cancel_policy_snapshot = models.JSONField(default=list, blank=True,
                                               help_text='Cancellation policy tiers snapshotted at booking time')

    # ── Dates ──────────────────────────────────────────────
    departure_date  = models.DateField(null=True, blank=True)

    # ── Pricing snapshot (locked at booking time) ──────────
    price_adult     = models.DecimalField(max_digits=10, decimal_places=2)
    price_child     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price     = models.DecimalField(max_digits=10, decimal_places=2)
    extras_cost     = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                           help_text='Cost of selected add-on extras at booking time')
    room_supplement_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                                help_text='Room type supplement (or discount) at booking time')
    deposit_paid    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency        = models.CharField(max_length=3, default='USD')

    # ── Payment ────────────────────────────────────────────
    # Which rail took the money. The two rails settle to different bank
    # accounts, so this is what reconciliation keys off.
    payment_method  = models.CharField(
        max_length=20, blank=True,
        choices=[
            ('stripe',  'Stripe (card)'),      # international rail, USD
            ('paypal',  'PayPal'),             # international rail, USD
            ('yookassa','YooKassa'),           # Russian rail, RUB
            ('sbp',     'СБП'),                # Russian rail, RUB
            ('bank',    'Bank transfer'),
        ],
    )
    yookassa_payment_id = models.CharField(max_length=60, blank=True, default='',
                                            help_text='YooKassa payment UUID')
    deposit_status  = models.CharField(
        max_length=12, default='pending',
        choices=[('pending','Pending'),('paid','Paid'),('failed','Failed')],
    )
    balance_due_date   = models.DateField(null=True, blank=True,
                                           help_text='Date balance payment is due')
    balance_paid       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_payment_id = models.CharField(max_length=64, blank=True, default='',
                                           help_text='YooKassa payment UUID for balance')
    balance_status     = models.CharField(
        max_length=12, default='pending',
        choices=[('pending','Pending'),('paid','Paid'),('failed','Failed')],
    )

    # ── Refund ─────────────────────────────────────────────
    refund_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                           help_text='Refund amount in tour currency')
    refund_status   = models.CharField(
        max_length=12, default='none',
        choices=[('none','None'),('pending','Pending'),('issued','Issued'),('manual','Manual transfer')],
    )

    # ── Timestamps ─────────────────────────────────────────
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)
    confirmed_at    = models.DateTimeField(null=True, blank=True)
    cancelled_at    = models.DateTimeField(null=True, blank=True)
    last_balance_reminder_sent = models.DateTimeField(null=True, blank=True,
        help_text='Last time an operator balance reminder was sent for this booking')

    # ── Commission and payout ──────────────────────────────
    # The rate is snapshotted the first time money is taken, never read live
    # from settings. If the platform rate changes, every booking already sold
    # must keep the deal it was sold under — a live lookup would silently
    # rewrite what past guides were owed.
    commission_pct  = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Platform commission % agreed at the time this booking was paid',
    )
    payout_status   = models.CharField(
        max_length=12, default='not_due',
        choices=[
            ('not_due', 'Not due yet'),   # trip has not run
            ('due',     'Due'),           # trip completed, guide is owed
            ('paid',    'Paid'),          # transfer sent
        ],
    )
    payout_sent_at   = models.DateTimeField(null=True, blank=True)
    payout_reference = models.CharField(
        max_length=80, blank=True, default='',
        help_text='Bank transfer reference, so a guide asking "was I paid?" has an answer',
    )

    # ── Cooling-off window ──────────────────────────────
    cooling_off_until = models.DateTimeField(
        null=True, blank=True,
        help_text=(
            'Penalty-free cancel deadline set at booking creation. '
            '+30 min if departure >7 days away, +15 min if ≤7 days. '
            'Takes precedence over all cancellation policy rules.'
        ),
    )

    class Meta:
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['tour', 'status']),
            models.Index(fields=['tourist', 'status']),
        ]

    def __str__(self):
        return f'{self.reference} | {self.tour.slug} | {self.status}'

    @property
    def price_per_person(self):
        return self.price_adult

    @property
    def balance_due(self):
        return max(0, float(self.total_price) - float(self.deposit_paid) - float(self.balance_paid))

    # ── The ledger ─────────────────────────────────────────
    # Everything keys off what was actually collected and kept, not off
    # total_price. A deposit-only booking, a late cancellation that kept a
    # penalty, and a full refund all fall out of the same three lines — and a
    # fully refunded booking correctly owes nobody anything.

    @property
    def amount_collected(self):
        """Every payment taken on this booking, in the tour's currency."""
        return round(float(self.deposit_paid) + float(self.balance_paid), 2)

    @property
    def amount_kept(self):
        """What the platform is still holding after any refund."""
        return round(max(0.0, self.amount_collected - float(self.refund_amount or 0)), 2)

    @property
    def effective_commission_pct(self):
        """
        The snapshot if there is one, otherwise today's rate.

        The fallback covers bookings taken before commission existed and
        bookings not yet paid — it is a display estimate, and the moment money
        is taken `snapshot_commission()` freezes the real number.
        """
        if self.commission_pct is not None:
            return float(self.commission_pct)
        from django.conf import settings as _s
        return float(getattr(_s, 'PLATFORM_COMMISSION_PCT', 15))

    @property
    def commission_amount(self):
        """
        Platform cut, charged on what was kept — including a cancellation
        penalty, because the payment processor keeps its fee on the original
        charge whether or not the trip ran, and the acquisition and support
        already happened.
        """
        return round(self.amount_kept * self.effective_commission_pct / 100, 2)

    @property
    def payout_amount(self):
        """What the guide is owed for this booking."""
        return round(self.amount_kept - self.commission_amount, 2)

    def snapshot_commission(self, save=True):
        """
        Freeze the rate on first payment. Idempotent: once set it is never
        touched again, so a later rate change cannot rewrite this booking.
        """
        if self.commission_pct is not None:
            return False
        from django.conf import settings as _s
        rate = getattr(self.tour.operator, 'commission_pct_override', None)
        if rate is None:
            rate = getattr(_s, 'PLATFORM_COMMISSION_PCT', 15)
        self.commission_pct = Decimal(str(rate))
        if save:
            self.save(update_fields=['commission_pct'])
        return True


class EnquiryMessage(models.Model):
    """
    Private tour enquiry — from the 'Request private dates' modal.
    Stores structured data from the form.
    Replies are stored in EnquiryReply — both tourist and operator can respond.
    """
    tour        = models.ForeignKey('tours.Tour', on_delete=models.CASCADE, related_name='enquiries')
    sender      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='sent_enquiries')

    # Sender contact (for guest enquiries before login)
    name        = models.CharField(max_length=120, blank=True)
    email       = models.EmailField(blank=True)

    # Enquiry details
    preferred_from  = models.DateField(null=True, blank=True)
    preferred_to    = models.DateField(null=True, blank=True)
    adults          = models.PositiveSmallIntegerField(default=2)
    children        = models.PositiveSmallIntegerField(default=0)
    infants         = models.PositiveSmallIntegerField(default=0)
    message         = models.TextField(blank=True)

    read_by_operator = models.BooleanField(default=False)
    operator_reply   = models.TextField(blank=True, default='')
    replied_at       = models.DateTimeField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Enquiry: {self.tour.slug} from {self.email or (self.sender.email if self.sender else "guest")}'


class EnquiryReply(models.Model):
    """Individual message in an enquiry thread (operator or tourist follow-up)."""
    enquiry     = models.ForeignKey(EnquiryMessage, on_delete=models.CASCADE, related_name='replies')
    sender      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='enquiry_replies')
    is_operator = models.BooleanField(default=False)
    body        = models.TextField()
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        role = 'operator' if self.is_operator else 'tourist'
        return f'Reply ({role}) on enquiry #{self.enquiry_id}'
