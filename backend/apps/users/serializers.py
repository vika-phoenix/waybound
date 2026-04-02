"""
apps/users/serializers.py
All request/response serializers for auth endpoints.
"""
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User


# ── Task 9: Email + password ───────────────────────────────────────────────

class TouristRegisterSerializer(serializers.ModelSerializer):
    """POST /api/v1/auth/register/tourist/"""
    password  = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label='Confirm password')

    class Meta:
        model  = User
        fields = ('email', 'password', 'password2', 'first_name', 'last_name', 'phone')

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password2': 'Passwords do not match.'})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = User(role=User.Role.TOURIST, **validated_data)
        user.set_password(password)
        user.save()
        return user


class OperatorRegisterSerializer(serializers.ModelSerializer):
    """POST /api/v1/auth/register/operator/"""
    password     = serializers.CharField(write_only=True, validators=[validate_password])
    password2    = serializers.CharField(write_only=True, label='Confirm password')
    company_name = serializers.CharField(max_length=120, required=False, allow_blank=True)

    class Meta:
        model  = User
        fields = (
            'email', 'password', 'password2',
            'first_name', 'last_name', 'phone',
            'company_name', 'country', 'bio',
        )

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password2': 'Passwords do not match.'})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        company_name = validated_data.pop('company_name', '')
        password = validated_data.pop('password')
        bio = validated_data.pop('bio', '')
        # Combine company name and bio if both provided
        if company_name and bio:
            full_bio = f'{company_name}\n\n{bio}'
        else:
            full_bio = bio or company_name
        user = User(role=User.Role.OPERATOR, bio=full_bio, **validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    """POST /api/v1/auth/login/"""
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(email=data['email'], password=data['password'])
        if not user:
            raise serializers.ValidationError('Invalid email or password.')
        if not user.is_active:
            raise serializers.ValidationError('This account has been deactivated.')
        data['user'] = user
        return data


class UserPublicSerializer(serializers.ModelSerializer):
    """Read-only public profile — safe to expose in tour listings and reviews."""
    full_name = serializers.ReadOnlyField()

    class Meta:
        model  = User
        fields = ('id', 'full_name', 'avatar', 'bio', 'country', 'role')


class UserMeSerializer(serializers.ModelSerializer):
    """
    GET  /api/v1/auth/me/   — full profile for the logged-in user
    PATCH /api/v1/auth/me/  — update editable fields
    """
    full_name           = serializers.ReadOnlyField()
    verification_status = serializers.SerializerMethodField()
    photo_url           = serializers.SerializerMethodField()
    credentials_files   = serializers.SerializerMethodField()

    def get_verification_status(self, obj):
        doc = obj.documents.filter(doc_type='identity').order_by('-submitted_at').first()
        return doc.status if doc else None

    def get_photo_url(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url

    def get_credentials_files(self, obj):
        if obj.role != 'operator':
            return []
        return list(obj.documents.filter(doc_type='credential').values('id', 'original_name', 'status', 'submitted_at'))

    class Meta:
        model  = User
        fields = (
            'id', 'email', 'phone',
            'first_name', 'last_name', 'full_name',
            'avatar', 'photo_url', 'bio', 'country', 'role',
            'experience_years',
            'is_verified', 'verification_status', 'credentials_files',
            'email_verified', 'phone_verified', 'marketing_emails',
            'telegram_chat_id',
            'payout_name', 'payout_bank', 'payout_account', 'payout_bik', 'payout_corr_account',
            'date_joined',
        )
        read_only_fields = (
            'id', 'email', 'role', 'full_name',
            'is_verified', 'verification_status', 'credentials_files',
            'email_verified', 'phone_verified', 'date_joined',
        )


class ChangePasswordSerializer(serializers.Serializer):
    """POST /api/v1/auth/change-password/"""
    current_password = serializers.CharField(write_only=True)
    new_password     = serializers.CharField(write_only=True, validators=[validate_password])
    new_password2    = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['new_password2']:
            raise serializers.ValidationError({'new_password2': 'Passwords do not match.'})
        return data


# ── Task 12: Phone OTP ─────────────────────────────────────────────────────

class OTPRequestSerializer(serializers.Serializer):
    """POST /api/v1/auth/otp/request/"""
    phone = serializers.CharField(max_length=20)

    def validate_phone(self, value):
        cleaned = value.strip().replace(' ', '').replace('-', '')
        if not cleaned.startswith('+'):
            cleaned = '+' + cleaned
        return cleaned


class OTPVerifySerializer(serializers.Serializer):
    """POST /api/v1/auth/otp/verify/"""
    phone = serializers.CharField(max_length=20)
    code  = serializers.CharField(max_length=6, min_length=4)

    def validate_phone(self, value):
        cleaned = value.strip().replace(' ', '').replace('-', '')
        if not cleaned.startswith('+'):
            cleaned = '+' + cleaned
        return cleaned


# ── Password reset ─────────────────────────────────────────────────────────

class PasswordResetRequestSerializer(serializers.Serializer):
    """POST /api/v1/auth/password-reset/"""
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """POST /api/v1/auth/password-reset/confirm/"""
    uid           = serializers.CharField()
    token         = serializers.CharField()
    new_password  = serializers.CharField(write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['new_password2']:
            raise serializers.ValidationError({'new_password2': 'Passwords do not match.'})
        return data
