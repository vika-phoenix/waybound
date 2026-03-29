"""
apps/tours/models.py  —  Task 18
Complete tour data model.

Design decisions:
- Tour        : the main listing (one row per tour, operator-owned)
- DepartureDate: fixed departure windows for multi-day tours
- StayBlock   : accommodation per night range
- DayItinerary: day-by-day plan (JSON is fine here, but separate model gives
                 better queryability for future calendar features)
- CancellationPolicy / CancelPeriod: tiered refund schedule
- TourPhoto   : ordered photo set (hero = order 0)
- TourFAQ     : operator-written Q&A

Relationships kept explicit (FK) rather than JSONField so the operator
dashboard can filter/sort by them, and the admin is navigable.
"""
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid


# ── Helpers ──────────────────────────────────────────────────────────────────

def tour_photo_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f'tours/{instance.tour.slug}/photos/{uuid.uuid4().hex[:8]}.{ext}'


def stay_photo_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f'tours/{instance.stay.tour.slug}/stays/{uuid.uuid4().hex[:8]}.{ext}'


# ── Main Tour model ───────────────────────────────────────────────────────────

class Tour(models.Model):

    class Status(models.TextChoices):
        DRAFT     = 'draft',     'Draft'
        REVIEW    = 'review',    'Under review'
        LIVE      = 'live',      'Live'
        PAUSED    = 'paused',    'Paused'
        ARCHIVED  = 'archived',  'Archived'

    class Category(models.TextChoices):
        TREKKING  = 'Trekking',     'Trekking'
        CULTURE   = 'Culture',      'Culture'
        WILDLIFE  = 'Wildlife',     'Wildlife'
        ADVENTURE = 'Adventure',    'Adventure'
        FOOD      = 'Food & Wine',  'Food & Wine'
        CYCLING   = 'Cycling',      'Cycling'
        WATER     = 'Water Sports', 'Water Sports'
        WINTER    = 'Winter Sports','Winter Sports'
        WELLNESS  = 'Wellness',     'Wellness'
        OTHER     = 'Other',        'Other'

    class Difficulty(models.TextChoices):
        EASY        = 'Easy',         'Easy'
        MODERATE    = 'Moderate',     'Moderate'
        CHALLENGING = 'Challenging',  'Challenging'
        EXPERT      = 'Expert',       'Expert'

    class TourType(models.TextChoices):
        MULTI  = 'multi',  'Multi-day (fixed departures)'
        SINGLE = 'single', 'Single-day (any date)'

    # ── Ownership ──────────────────────────────────────────
    operator    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tours',
        limit_choices_to={'role': 'operator'},
    )

    # ── Identity ───────────────────────────────────────────
    title       = models.CharField(max_length=160)
    slug        = models.SlugField(max_length=180, unique=True, blank=True)
    status      = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)

    # ── Classification ─────────────────────────────────────
    category    = models.CharField(max_length=20, choices=Category.choices, default=Category.TREKKING, db_index=True)
    categories  = models.JSONField(default=list, blank=True, help_text='Multi-select list of category strings')
    difficulty  = models.CharField(max_length=12, choices=Difficulty.choices, default=Difficulty.MODERATE)
    tour_type   = models.CharField(max_length=8,  choices=TourType.choices,  default=TourType.MULTI)

    # ── Geography ──────────────────────────────────────────
    country     = models.CharField(max_length=80, db_index=True)
    destination = models.CharField(max_length=120)   # city / region display name
    region      = models.CharField(max_length=120, blank=True)
    latitude    = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude   = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    timezone    = models.CharField(
        max_length=50, default='Europe/Moscow', blank=True,
        help_text='IANA timezone for departure city (used for cancel/deposit deadlines)',
    )

    # ── Timing ─────────────────────────────────────────────
    days        = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(60)])

    # ── Pricing ────────────────────────────────────────────
    price_adult = models.DecimalField(max_digits=10, decimal_places=2)
    price_child = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                       help_text='Leave blank to default to 85% of adult price')
    currency    = models.CharField(max_length=3, default='RUB')
    max_group   = models.PositiveSmallIntegerField(default=12)
    min_group   = models.PositiveSmallIntegerField(default=1)

    # ── Payment policy ─────────────────────────────────────
    deposit_pct      = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Deposit percentage required at booking (0–100)',
    )
    balance_due_days = models.PositiveSmallIntegerField(
        default=30,
        help_text='Days before departure when balance payment is due',
    )

    # ── Content ────────────────────────────────────────────
    description     = models.TextField(blank=True, help_text='HTML allowed (rich text)')
    highlights      = models.JSONField(default=list, blank=True,
                                        help_text='List of short highlight strings')
    includes        = models.JSONField(default=list, blank=True)
    excludes        = models.JSONField(default=list, blank=True)
    requirements    = models.TextField(blank=True)
    meeting_point   = models.TextField(blank=True)
    meeting_time    = models.CharField(max_length=20, blank=True, default='',
                                        help_text='Daily meet-up time e.g. "09:00 AM"')
    end_point       = models.TextField(blank=True)

    # ── Extra operator info ─────────────────────────────────
    language       = models.CharField(max_length=100, blank=True, default='')
    languages      = models.JSONField(default=list, blank=True,
                                       help_text='Multi-select language list e.g. ["English","Russian"]')
    difficulty_note = models.CharField(max_length=300, blank=True, default='',
                                        help_text='Operator note on physical demands')
    extras         = models.JSONField(default=list, blank=True,
                                       help_text='Optional add-ons: [{name, description, price_per_person}]')
    min_age        = models.PositiveSmallIntegerField(null=True, blank=True)
    max_age        = models.PositiveSmallIntegerField(null=True, blank=True)
    is_private     = models.BooleanField(default=False)
    video_url      = models.URLField(blank=True, default='')
    getting_there  = models.TextField(blank=True, default='')
    organiser_note = models.TextField(blank=True, default='')

    # ── Display ────────────────────────────────────────────
    emoji       = models.CharField(max_length=8, blank=True, default='🌍')
    tags        = models.JSONField(default=list, blank=True, null=True, help_text='Short keyword tags')

    # ── Stats (denormalised for speed) ─────────────────────
    rating          = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    review_count    = models.PositiveIntegerField(default=0)
    booking_count   = models.PositiveIntegerField(default=0)

    # ── Timestamps ─────────────────────────────────────────
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    # ── Change-notification penalty-free window ─────────────
    # Set to now + window_hours whenever operator edits material fields.
    # While datetime.now() < this value, tourist cancellations are penalty-free.
    change_cancel_window_until = models.DateTimeField(
        null=True, blank=True,
        help_text='Tourists may cancel penalty-free until this datetime after a material change.',
    )

    class Meta:
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['status', 'category']),
            models.Index(fields=['country', 'status']),
        ]

    def __str__(self):
        return f'{self.title} [{self.status}]'

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)
            slug = base
            n = 1
            while Tour.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        # Guard against NULL being saved into non-nullable JSONFields
        if self.tags is None:
            self.tags = []
        if self.categories is None:
            self.categories = []
        # Keep legacy category in sync with first item of categories list
        if self.categories:
            self.category = self.categories[0]
        super().save(*args, **kwargs)

    @property
    def price_child_effective(self):
        if self.price_child is not None:
            return self.price_child
        return round(float(self.price_adult) * 0.85, 2)

    @property
    def hero_photo(self):
        return self.photos.filter(order=0).first() or self.photos.order_by('order').first()

    @property
    def spots_left_for_next_departure(self):
        nxt = self.departures.filter(
            status=DepartureDate.Status.OPEN
        ).order_by('start_date').first()
        return nxt.spots_left if nxt else 0


# ── Departure windows (multi-day tours) ──────────────────────────────────────

class DepartureDate(models.Model):

    class Status(models.TextChoices):
        OPEN        = 'open',       'Open'
        GUARANTEED  = 'guaranteed', 'Guaranteed'
        FULL        = 'full',       'Full'
        CANCELLED   = 'cancelled',  'Cancelled'

    tour        = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='departures')
    start_date  = models.DateField(db_index=True)
    end_date    = models.DateField()
    spots_total = models.PositiveSmallIntegerField()
    spots_left  = models.PositiveSmallIntegerField()
    status      = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                          help_text='Leave blank to use tour base price')
    notes       = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['start_date']
        unique_together = [('tour', 'start_date')]

    def __str__(self):
        return f'{self.tour.slug} | {self.start_date} → {self.end_date}'

    @property
    def price(self):
        return self.price_override or self.tour.price_adult


# ── Day itinerary ─────────────────────────────────────────────────────────────

class DayItinerary(models.Model):
    tour        = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='itinerary')
    day_number  = models.PositiveSmallIntegerField()
    title       = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    meals       = models.CharField(max_length=80, blank=True, help_text='e.g. Breakfast, Dinner')
    elevation   = models.CharField(max_length=40, blank=True, help_text='e.g. +600m / -200m')

    class Meta:
        ordering = ['day_number']
        unique_together = [('tour', 'day_number')]

    def __str__(self):
        return f'{self.tour.slug} Day {self.day_number}: {self.title}'


# ── Accommodation / stay blocks ───────────────────────────────────────────────

class StayBlock(models.Model):

    class Comfort(models.TextChoices):
        BUDGET    = 'Budget',    'Budget'
        STANDARD  = 'Standard',  'Standard'
        SUPERIOR  = 'Superior',  'Superior'
        LUXURY    = 'Luxury',    'Luxury'

    class PropertyType(models.TextChoices):
        HOTEL      = 'Hotel',            'Hotel'
        HOSTEL     = 'Hostel',           'Hostel'
        GUESTHOUSE = 'Guesthouse',       'Guesthouse'
        CAMPING    = 'Camping/glamping',  'Camping / glamping'
        HOMESTAY   = 'Homestay',         'Homestay'
        HUT        = 'Mountain hut',     'Mountain hut'
        OTHER      = 'Other',            'Other'

    tour            = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='stays')
    property_name   = models.CharField(max_length=160)
    property_type   = models.CharField(max_length=20, choices=PropertyType.choices, blank=True)
    comfort_level   = models.CharField(max_length=10, choices=Comfort.choices, blank=True)
    night_from      = models.PositiveSmallIntegerField(help_text='First night covered (1-indexed)')
    night_to        = models.PositiveSmallIntegerField(help_text='Last night covered')
    room_types      = models.JSONField(default=list, blank=True,
                                        help_text='List of {name, price_supplement} dicts')

    class Meta:
        ordering = ['night_from']

    def __str__(self):
        return f'{self.tour.slug} | {self.property_name} (nights {self.night_from}–{self.night_to})'


# ── Property photos (per stay block) ─────────────────────────────────────────

class PropertyPhoto(models.Model):
    stay    = models.ForeignKey(StayBlock, on_delete=models.CASCADE, related_name='photos')
    image   = models.ImageField(upload_to=stay_photo_path)
    order   = models.PositiveSmallIntegerField(default=0)
    caption = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.stay} photo #{self.order}'


# ── Cancellation policy ────────────────────────────────────────────────────────

class CancelPeriod(models.Model):
    """One row = one tier of the cancellation schedule."""
    tour            = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='cancel_policy')
    days_before_min = models.PositiveSmallIntegerField(help_text='Days before departure (lower bound)')
    days_before_max = models.PositiveSmallIntegerField(null=True, blank=True,
                                                        help_text='Days before departure (upper bound, null = ∞)')
    penalty_pct     = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Percentage of total price charged as penalty (0 = full refund)',
    )
    label           = models.CharField(max_length=80, blank=True,
                                        help_text='e.g. "Full refund", "50% penalty"')

    class Meta:
        ordering = ['-days_before_max']

    def __str__(self):
        return f'{self.tour.slug} | {self.penalty_pct}% if <{self.days_before_min}d'


# ── Photos ────────────────────────────────────────────────────────────────────

class TourPhoto(models.Model):
    tour    = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='photos')
    image   = models.ImageField(upload_to=tour_photo_path)
    order   = models.PositiveSmallIntegerField(default=0, help_text='0 = hero image')
    caption = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.tour.slug} photo #{self.order}'


# ── FAQ ───────────────────────────────────────────────────────────────────────

class TourFAQ(models.Model):
    tour     = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='faqs')
    question = models.CharField(max_length=300)
    answer   = models.TextField()
    order    = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.tour.slug} FAQ: {self.question[:60]}'


# ── Saved tours (tourist wishlist) ────────────────────────────────────────────

class SavedTour(models.Model):
    tourist  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_tours')
    tour     = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='saved_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tourist', 'tour')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.tourist.email} saved {self.tour.slug}'


# ── Waitlist for sold-out dates ───────────────────────────────────────────────

class WaitlistEntry(models.Model):
    tour            = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='waitlist')
    departure       = models.ForeignKey('DepartureDate', on_delete=models.CASCADE,
                                        null=True, blank=True, related_name='waitlist')
    email           = models.EmailField()
    name            = models.CharField(max_length=100, blank=True)
    departure_label = models.CharField(max_length=100, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tour', 'email', 'departure_label')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} on waitlist for {self.tour.slug}'
