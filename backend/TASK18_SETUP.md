# Task 18 — Backend Setup

## Run these commands after copying files into the project

```bash
# 1. Apply migrations (tours first, bookings depend on it)
python manage.py migrate tours
python manage.py migrate bookings

# 2. Load test data (requires operator user pk=1 and tourist user pk=2 to exist)
python manage.py loaddata apps/tours/fixtures/initial_tours.json
python manage.py loaddata apps/bookings/fixtures/dashboard_test.json

# 3. Install new dependency (Pillow for ImageField, django-filter)
pip install Pillow django-filter
```

## Files changed / added

| File | Action |
|------|--------|
| apps/tours/models.py | Complete rewrite — Tour, DepartureDate, DayItinerary, StayBlock, CancelPeriod, TourPhoto, TourFAQ, SavedTour |
| apps/tours/serializers.py | New — TourListSerializer, TourDetailSerializer, TourWriteSerializer, SavedTourSerializer, OperatorTourListSerializer |
| apps/tours/views.py | New — tour_list, tour_detail, saved_tour_list, saved_tour_toggle, tour_photo_upload, operator_tour_list, tour_publish |
| apps/tours/urls.py | Updated — all tour routes |
| apps/tours/permissions.py | New — IsOperator, IsOperatorOwner |
| apps/tours/admin.py | New — full admin with inlines |
| apps/tours/migrations/0001_initial.py | New |
| apps/tours/fixtures/initial_tours.json | New — 2 tours, departures, itinerary, stays, policies, FAQs |
| apps/bookings/models.py | Complete rewrite — Booking, EnquiryMessage |
| apps/bookings/serializers.py | New — BookingCreateSerializer, BookingDetailSerializer, OperatorBookingSerializer, EnquiryCreateSerializer |
| apps/bookings/views.py | New — booking_list, booking_detail, booking_cancel, operator_booking_list, booking_confirm, enquiry_list |
| apps/bookings/urls.py | Updated |
| apps/bookings/admin.py | New |
| apps/bookings/migrations/0001_initial.py | New |
| apps/bookings/fixtures/dashboard_test.json | New — 2 test bookings |
| waybound/api_urls.py | Updated — all routes documented |

## Key API endpoints

### Public (no auth)
- `GET /api/v1/tours/` — list live tours, supports ?category=&country=&q=&min_price=&max_price=&min_days=&max_days=&difficulty=&order=
- `GET /api/v1/tours/<slug>/` — full tour detail

### Tourist (JWT required)
- `GET/POST /api/v1/bookings/` — list own bookings / create booking
- `GET /api/v1/bookings/<pk>/` — booking detail
- `PATCH /api/v1/bookings/<pk>/cancel/` — cancel booking
- `GET /api/v1/tours/saved/` — wishlist
- `POST/DELETE /api/v1/tours/<slug>/save/` — save / unsave

### Operator (JWT + role=operator)
- `POST /api/v1/tours/` — create tour (nested JSON)
- `PATCH /api/v1/tours/<slug>/` — edit tour
- `PATCH /api/v1/tours/<slug>/publish/` — submit for review
- `GET /api/v1/tours/operator/` — own tours list
- `POST /api/v1/tours/<slug>/photos/` — upload photo (multipart)
- `DELETE /api/v1/tours/<slug>/photos/<id>/` — delete photo
- `GET /api/v1/bookings/operator/` — bookings for own tours
- `PATCH /api/v1/bookings/<pk>/confirm/` — confirm booking
- `GET /api/v1/bookings/enquiries/` — private tour enquiries

### Anyone
- `POST /api/v1/bookings/enquiries/` — submit private tour enquiry

## Next: Task 18 frontend wiring
Connect operator-tour-create.html form → POST/PATCH /api/v1/tours/
Connect operator-dashboard.html → GET /api/v1/tours/operator/ and GET /api/v1/bookings/operator/
Replace all demo data with real API calls.
