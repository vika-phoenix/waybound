"""
apps/users/models.py
Custom User model — extends AbstractBaseUser so we own every field.
Role field distinguishes tourists from operators/guides.
Phone field added now (OTP auth in Task 12).
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


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

    # ── Payout (operators only) ────────────────────────────
    payout_name         = models.CharField(max_length=120, blank=True, default='')
    payout_bank         = models.CharField(max_length=120, blank=True, default='')
    payout_account      = models.CharField(max_length=30, blank=True, default='')
    payout_bik          = models.CharField(max_length=12, blank=True, default='')
    payout_corr_account = models.CharField(max_length=30, blank=True, default='')

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
        return f'{self.first_name} {self.last_name}'.strip() or self.email


class VerificationDocument(models.Model):
    class Status(models.TextChoices):
        PENDING  = 'pending',  'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    class DocType(models.TextChoices):
        IDENTITY   = 'identity',   'Identity document'
        CREDENTIAL = 'credential', 'Guide credential'

    operator      = models.ForeignKey('User', on_delete=models.CASCADE, related_name='documents')
    document      = models.FileField(upload_to='verification/')
    doc_type      = models.CharField(max_length=12, choices=DocType.choices, default=DocType.IDENTITY)
    original_name = models.CharField(max_length=255, blank=True, default='')
    submitted_at  = models.DateTimeField(auto_now_add=True)
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    status        = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    admin_notes   = models.TextField(blank=True)

    def __str__(self):
        return f'{self.operator.email} — {self.doc_type} — {self.status}'


class OTPCode(models.Model):
    """Short-lived SMS OTP — used by Task 12 phone auth."""
    phone      = models.CharField(max_length=20)
    code       = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used       = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'OTP Code'

    def __str__(self):
        return f'OTP for {self.phone}'
