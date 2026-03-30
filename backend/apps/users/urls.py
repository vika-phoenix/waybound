"""
apps/users/urls.py
All auth endpoints under /api/v1/auth/
"""
from django.urls import path
from . import views

urlpatterns = [
    # Utility
    path('health/', views.health, name='auth-health'),

    # Task 9: Email + password
    path('register/tourist/',   views.register_tourist,  name='register-tourist'),
    path('register/operator/',  views.register_operator, name='register-operator'),
    path('login/',              views.login,             name='login'),
    path('logout/',             views.logout,            name='logout'),
    path('me/',                 views.me,                name='me'),
    path('change-password/',    views.change_password,   name='change-password'),

    # Password reset (email flow)
    path('password-reset/',         views.password_reset_request, name='password-reset'),
    path('password-reset/confirm/', views.password_reset_confirm, name='password-reset-confirm'),

    # Tasks 10+11: Social OAuth JWT exchange
    path('social/token/', views.social_token_exchange, name='social-token'),

    # Task 12: Phone OTP
    path('otp/request/', views.otp_request, name='otp-request'),
    path('otp/verify/',  views.otp_verify,  name='otp-verify'),

    # Operator verification & documents
    path('verify/', views.verify_document, name='verify-document'),
    path('me/documents/', views.user_documents, name='user-documents'),

    # Social account connections
    path('social/connections/',            views.social_connections,  name='social-connections'),
    path('social/connections/<str:provider>/', views.social_disconnect, name='social-disconnect'),
]
