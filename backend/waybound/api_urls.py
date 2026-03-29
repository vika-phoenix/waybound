"""
waybound/api_urls.py  —  Task 18 update
All REST API routes under /api/v1/
"""
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import contact_view

urlpatterns = [
    path('auth/', include('apps.users.urls')),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('tours/', include('apps.tours.urls')),
    path('bookings/', include('apps.bookings.urls')),
    path('payments/', include('apps.payments.urls')),
    path('reviews/', include('apps.reviews.urls')),
    path('contact/', contact_view.contact, name='contact'),
]
