"""
apps/tours/urls.py  —  Task 18

/api/v1/tours/ routes
"""
from django.urls import path
from . import views

urlpatterns = [
    # ── Public + operator create ──────────────────────────
    # GET  /api/v1/tours/          — list (public)
    # POST /api/v1/tours/          — create (operator)
    path('', views.tour_list, name='tour-list'),

    # ── Operator dashboard ────────────────────────────────
    # GET /api/v1/tours/operator/  — own tours only
    path('operator/', views.operator_tour_list, name='operator-tour-list'),

    # ── Saved (tourist wishlist) ──────────────────────────
    # GET /api/v1/tours/saved/
    path('saved/', views.saved_tour_list, name='saved-tour-list'),

    # ── Tour detail ───────────────────────────────────────
    # GET   /api/v1/tours/<slug>/  — public detail
    # PATCH /api/v1/tours/<slug>/  — operator edit
    # DELETE /api/v1/tours/<slug>/ — operator archive
    path('<slug:slug>/', views.tour_detail, name='tour-detail'),

    # ── Publish / submit for review ───────────────────────
    # PATCH /api/v1/tours/<slug>/publish/
    path('<slug:slug>/publish/', views.tour_publish, name='tour-publish'),

    # ── Save / unsave ─────────────────────────────────────
    # POST   /api/v1/tours/<slug>/save/
    # DELETE /api/v1/tours/<slug>/save/
    path('<slug:slug>/save/', views.saved_tour_toggle, name='saved-tour-toggle'),

    # ── Photos ────────────────────────────────────────────
    # POST   /api/v1/tours/<slug>/photos/
    path('<slug:slug>/photos/', views.tour_photo_upload, name='tour-photo-upload'),
    # DELETE /api/v1/tours/<slug>/photos/<photo_id>/
    path('<slug:slug>/photos/<int:photo_id>/', views.tour_photo_delete, name='tour-photo-delete'),

    # ── Property (stay) photos ────────────────────────────
    # POST   /api/v1/tours/<slug>/stays/<night_from>/photos/
    path('<slug:slug>/stays/<int:night_from>/photos/', views.stay_photo_upload, name='stay-photo-upload'),
    # DELETE /api/v1/tours/<slug>/stays/photos/<photo_id>/
    path('<slug:slug>/stays/photos/<int:photo_id>/', views.stay_photo_delete, name='stay-photo-delete'),

    # ── Waitlist ───────────────────────────────────────────
    # POST /api/v1/tours/<slug>/waitlist/
    path('<slug:slug>/waitlist/', views.waitlist_join, name='tour-waitlist'),
]
