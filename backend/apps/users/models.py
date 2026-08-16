"""
apps/users/models.py
Custom User model — extends AbstractBaseUser so we own every field.
Role field distinguishes tourists from operators/guides.
Supports both email/password and social OAuth login (Google, Yandex, VK).
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from .storages import private_media_storage


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        extra.setdefault('role', User.Role.ADMIN)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        TOURIST  = 'tourist',  'Tourist'
        OPERATOR = 'operator', 'Operator / Guide'
        ADMIN    = 'admin',    'Admin'

    # ── Core identity ──────────────────────────────────────
    email        = models.EmailField(unique=True)
    phone        = models.CharField(max_length=20, blank=True, default='')
    first_name   = models.CharField(max_length=60, blank=True)
    last_name    = models.CharField(max_length=60, blank=True)
    role         = models.CharField(max_length=10, choices=Role.choices, default=Role.TOURIST)

    # ── Profile ────────────────────────────────────────────
    avatar           = models.ImageField(upload_to='avatars/', blank=True, null=True)
    bio              = models.TextField(blank=True)

    class Language(models.TextChoices):
        EN = 'en', 'English'
        RU = 'ru', 'Русский'

    language = models.CharField(
        max_length=5, choices=Language.choices, default=Language.EN, db_index=True,
        help_text='Which language to write to this person in. Set from the page '
                  'they signed up on, and changeable in their settings. The site '
                  'has always been bilingual; the emails were not.',
    )
    country          = models.CharField(max_length=80, blank=True)
    experience_years = models.CharField(max_length=20, blank=True, default='',
                                        help_text='Operator: years of guiding experience (e.g. "5–10 years")')

    # ── Flags ──────────────────────────────────────────────
    is_active    = models.BooleanField(default=True)
    is_staff     = models.BooleanField(default=False)
    is_verified  = models.BooleanField(default=False)  # operator ID verification
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    marketing_emails    = models.BooleanField(default=False)
    telegram_chat_id    = models.CharField(max_length=32, blank=True, default='',
                                            help_text='Operator Telegram chat ID for instant notifications')

    # ── What they told us when they applied ────────────────
    #
    # The guide signup form has always asked these six questions and thrown
    # every answer away. They are kept as application answers, not as live
    # profile truth: tour_types and typical_group_size overlap with a tour's
    # own categories and max_group, and if they were treated as current fact
    # the two would contradict each other the first time a guide listed
    # something different. Read as "this is what they said when they applied"
    # there is no contradiction to resolve.
    #
    # languages and certifications also give the verification screen something
    # to check the uploaded documents against — until now an admin opened a
    # passport scan with no claim to compare it to.
    languages          = models.CharField(max_length=200, blank=True, default='',
                                          help_text='Languages this guide says they guide in')
    certifications     = models.TextField(blank=True, default='',
                                          help_text='Claimed, not verified — check against their uploaded documents')
    tour_types         = models.JSONField(default=list, blank=True,
                                          help_text='Kinds of tour they said they run, at application time')
    typical_group_size = models.CharField(max_length=40, blank=True, default='')
    profile_link       = models.CharField(max_length=300, blank=True, default='',
                                          help_text='Existing reviews or profile they offered as evidence')
    referral_source    = models.CharField(max_length=80, blank=True, default='',
                                          help_text='How they heard about us. Attribution only, never shown.')

    # When this guide agreed to the Terms for Travel Experts.
    #
    # The signup form has always displayed the terms and refused to submit
    # without the tick — but the answer was never sent anywhere, so nothing was
    # recorded. The upgrade path did not ask at all. Both write this now, which
    # means "did they agree, and when" is a question with an answer.
    guide_terms_accepted_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When this guide accepted the Terms for Travel Experts')

    # ── Payout (operators only) ────────────────────────────
    # Two shapes, because a bank account is described differently depending on
    # where it is. The Russian fields below were the only ones for a while,
    # which meant a guide in Georgia or Armenia — most of the target market —
    # had no way to give details anyone could actually pay.
    class PayoutType(models.TextChoices):
        RUSSIA        = 'ru',   'Russian bank account'
        INTERNATIONAL = 'intl', 'Bank account outside Russia'

    payout_type         = models.CharField(max_length=8, blank=True, default='',
                                           choices=PayoutType.choices)
    # Shared by both shapes.
    payout_name         = models.CharField(max_length=120, blank=True, default='')
    payout_bank         = models.CharField(max_length=120, blank=True, default='')
    # Russian domestic transfer.
    payout_account      = models.CharField(max_length=30, blank=True, default='')
    payout_bik          = models.CharField(max_length=12, blank=True, default='')
    payout_corr_account = models.CharField(max_length=30, blank=True, default='')
    # Everywhere else.
    payout_iban         = models.CharField(max_length=34, blank=True, default='')
    payout_swift        = models.CharField(max_length=11, blank=True, default='')
    payout_bank_country = models.CharField(max_length=60, blank=True, default='')

    @property
    def payout_ready(self):
        """
        Whether this guide could actually be paid.

        Read the shape they chose, not whichever fields happen to be filled —
        a half-migrated profile can carry stale values from the other form.
        """
        if not self.payout_name:
            return False
        if self.payout_type == self.PayoutType.INTERNATIONAL:
            return bool(self.payout_iban and self.payout_swift)
        if self.payout_type == self.PayoutType.RUSSIA:
            return bool(self.payout_account and self.payout_bik)
        # Older profiles predate the choice; they can only be Russian.
        return bool(self.payout_account and self.payout_bik)

    @property
    def payout_summary(self):
        """One line to copy into a banking app, in the right format."""
        if not self.payout_ready:
            return ''
        if self.payout_type == self.PayoutType.INTERNATIONAL:
            parts = [self.payout_name, self.payout_bank, f'IBAN {self.payout_iban}',
                     f'SWIFT {self.payout_swift}', self.payout_bank_country]
        else:
            parts = [self.payout_name, self.payout_bank, f'acct {self.payout_account}',
                     f'BIK {self.payout_bik}']
            if self.payout_corr_account:
                parts.append(f'corr {self.payout_corr_account}')
        return ' · '.join(p for p in parts if p)
    # Left null for everyone on the standard rate. Set it only where a guide
    # has actually negotiated something different, so the platform rate stays
    # one number in settings rather than a value copied onto every account.
    commission_pct_override = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Overrides the platform commission % for this guide. Leave blank for the standard rate.',
    )

    # ── Timestamps ─────────────────────────────────────────
    date_joined  = models.DateTimeField(default=timezone.now)
    last_login   = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        return f'{self.email} ({self.role})'

    @property
    def full_name(self):
        """
        For staff screens and our own alerts, where falling back to the email
        is the useful thing. Never render this on a page a visitor can see —
        use public_display_name.
        """
        return f'{self.first_name} {self.last_name}'.strip() or self.email

    @property
    def public_display_name(self):
        """
        A name safe to show a stranger.

        Names are optional, and full_name falls back to the email address —
        so a guide who skipped theirs had a personal email printed on every
        tour page, and a traveller who skipped theirs had one printed under
        their review. Neither of them ever agreed to that.
        """
        name = f'{self.first_name} {self.last_name}'.strip()
        if name:
            return name
        return 'Kavkazland Guide' if self.role == self.Role.OPERATOR else 'Traveller'


class VerificationDocument(models.Model):
    class Status(models.TextChoices):
        PENDING  = 'pending',  'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    class DocType(models.TextChoices):
        IDENTITY   = 'identity',   'Identity document'
        CREDENTIAL = 'credential', 'Guide credential'

    operator      = models.ForeignKey('User', on_delete=models.CASCADE, related_name='documents')
    document      = models.FileField(upload_to='verification/', storage=private_media_storage)
    doc_type      = models.CharField(max_length=12, choices=DocType.choices, default=DocType.IDENTITY)
    original_name = models.CharField(max_length=255, blank=True, default='')
    submitted_at  = models.DateTimeField(auto_now_add=True)
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    status        = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    admin_notes   = models.TextField(blank=True)
    purged_at     = models.DateTimeField(
        null=True, blank=True,
        help_text='When the file itself was deleted under the retention rule. '
                  'The row stays so the verification decision remains on record.',
    )

    def __str__(self):
        return f'{self.operator.email} — {self.doc_type} — {self.status}'

    def purge_file(self):
        """
        Delete the scan, keep the decision.

        A passport is needed to *make* the verification decision, not to hold
        afterwards — keeping it forever is data you do not need and a breach
        would expose. The row survives, so who was verified, when, and by what
        kind of document is still auditable; only the image goes.
        """
        if self.purged_at:
            return False
        if self.document:
            # storage delete first: if the row saves and this fails, the file is
            # orphaned with nothing left pointing at it.
            self.document.delete(save=False)
        self.purged_at = timezone.now()
        self.save(update_fields=['document', 'purged_at'])
        return True


class OTPCode(models.Model):
    """Short-lived SMS OTP for phone number verification."""
    phone      = models.CharField(max_length=20)
    code       = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used       = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'OTP Code'

    def __str__(self):
        return f'OTP for {self.phone}'
