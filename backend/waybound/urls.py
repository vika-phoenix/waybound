"""
waybound/urls.py  —  Root URL configuration
All API endpoints are namespaced under /api/v1/
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse

def health(request):
    return JsonResponse({'status': 'ok'})

urlpatterns = [
    path('api/v1/health/', health),
    # Django admin
    path('admin/', admin.site.urls),

    # Auth (allauth — used for OAuth callbacks, email confirm links)
    path('accounts/', include('allauth.urls')),

    # REST API v1
    path('api/v1/', include('waybound.api_urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
