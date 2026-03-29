"""
apps/payments/urls.py
"""
from django.urls import path
from . import views

urlpatterns = [
    path('initiate/',  views.initiate_payment,  name='payment-initiate'),
    path('webhook/',   views.yookassa_webhook,   name='payment-webhook'),
]
