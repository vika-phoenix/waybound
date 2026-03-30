from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.utils.html import format_html
from .models import User, OTPCode, VerificationDocument


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ('email', 'full_name', 'role', 'is_active', 'email_verified', 'marketing_emails', 'date_joined')
    list_filter   = ('role', 'is_active', 'is_staff', 'email_verified', 'marketing_emails')
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering      = ('-date_joined',)

    fieldsets = (
        (None,           {'fields': ('email', 'password')}),
        ('Personal',     {'fields': ('first_name', 'last_name', 'phone', 'avatar', 'bio', 'country')}),
        ('Payout',       {'fields': ('payout_name', 'payout_bank', 'payout_account', 'payout_bik', 'payout_corr_account'),
                          'classes': ('collapse',)}),
        ('Role & flags', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser',
                                     'email_verified', 'phone_verified', 'marketing_emails')}),
        ('Permissions',  {'fields': ('groups', 'user_permissions')}),
        ('Timestamps',   {'fields': ('date_joined', 'last_login')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('email', 'password1', 'password2', 'role'),
        }),
    )
    readonly_fields = ('date_joined', 'last_login')


@admin.register(VerificationDocument)
class VerificationDocumentAdmin(admin.ModelAdmin):
    list_display  = ('operator_email', 'doc_type', 'original_name', 'status', 'submitted_at', 'reviewed_at', 'document_link')
    list_filter   = ('status', 'doc_type')
    search_fields = ('operator__email', 'original_name')
    readonly_fields = ('submitted_at', 'reviewed_at', 'document_link')
    actions = ['approve_verification', 'reject_verification']

    def operator_email(self, obj): return obj.operator.email
    operator_email.short_description = 'Operator'

    def document_link(self, obj):
        if obj.document:
            return format_html('<a href="{}" target="_blank">View document</a>', obj.document.url)
        return '—'
    document_link.short_description = 'Document'

    def approve_verification(self, request, queryset):
        from django.core.mail import send_mail
        from django.conf import settings as s
        for vdoc in queryset:
            vdoc.status = VerificationDocument.Status.APPROVED
            vdoc.reviewed_at = timezone.now()
            vdoc.save()
            vdoc.operator.is_verified = True
            vdoc.operator.save(update_fields=['is_verified'])
            send_mail(
                'Waybound: Verification approved',
                f'Hi {vdoc.operator.first_name},\n\nYour operator account has been verified. You can now submit tours for review.\n\nThe Waybound Team',
                getattr(s, 'DEFAULT_FROM_EMAIL', 'noreply@waybound.com'),
                [vdoc.operator.email], fail_silently=True,
            )
        self.message_user(request, f'{queryset.count()} operator(s) approved.', messages.SUCCESS)
    approve_verification.short_description = 'Approve selected verifications'

    def reject_verification(self, request, queryset):
        from django.core.mail import send_mail
        from django.conf import settings as s
        for vdoc in queryset:
            vdoc.status = VerificationDocument.Status.REJECTED
            vdoc.reviewed_at = timezone.now()
            vdoc.save()
            send_mail(
                'Waybound: Verification rejected',
                f'Hi {vdoc.operator.first_name},\n\nYour verification document was not accepted.\nReason: {vdoc.admin_notes or "Please resubmit a clearer document."}\n\nThe Waybound Team',
                getattr(s, 'DEFAULT_FROM_EMAIL', 'noreply@waybound.com'),
                [vdoc.operator.email], fail_silently=True,
            )
        self.message_user(request, f'{queryset.count()} verification(s) rejected.', messages.WARNING)
    reject_verification.short_description = 'Reject selected verifications'


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display  = ('phone', 'code', 'created_at', 'used')
    list_filter   = ('used',)
    search_fields = ('phone',)
