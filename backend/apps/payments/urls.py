"""
apps/payments/urls.py
"""
from django.urls import path
from . import views

urlpatterns = [
    path('methods/',   views.payment_methods,   name='payment-methods'),
    path('initiate/',  views.initiate_payment,  name='payment-initiate'),
    path('webhook/',   views.yookassa_webhook,   name='payment-webhook'),
    path('stripe/webhook/', views.stripe_webhook, name='payment-stripe-webhook'),
    path('paypal/webhook/', views.paypal_webhook, name='payment-paypal-webhook'),
]
