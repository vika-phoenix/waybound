"""
apps/bookings/urls.py  —  Task 18
"""
from django.urls import path
from . import views

urlpatterns = [
    # Tourist
    path('',                          views.booking_list,           name='booking-list'),
    path('<int:pk>/',                  views.booking_detail,         name='booking-detail'),
    path('<int:pk>/cancel/',           views.booking_cancel,         name='booking-cancel'),
    path('<int:pk>/cancel-preview/',   views.booking_cancel_preview, name='booking-cancel-preview'),

    # Operator
    path('operator/',                  views.operator_booking_list,  name='operator-booking-list'),
    path('<int:pk>/confirm/',          views.booking_confirm,        name='booking-confirm'),
    path('<int:pk>/message/',          views.operator_message,       name='operator-message'),

    # Enquiries
    path('enquiries/',                 views.enquiry_list,           name='enquiry-list'),
    path('enquiries/mine/',            views.my_enquiries,           name='my-enquiries'),
    path('enquiries/<int:pk>/reply/',         views.enquiry_reply,          name='enquiry-reply'),
    path('enquiries/<int:pk>/tourist-reply/', views.enquiry_tourist_reply,  name='enquiry-tourist-reply'),
    path('enquiries/<int:pk>/read/',          views.enquiry_mark_read,      name='enquiry-read'),
]
