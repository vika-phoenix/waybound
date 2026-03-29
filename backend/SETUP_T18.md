# Task 18 Backend — Setup Instructions

## Files delivered

```
apps/tours/
  models.py          ← Tour, DepartureDate, DayItinerary, StayBlock,
                        CancelPeriod, TourPhoto, TourFAQ, SavedTour
  serializers.py     ← TourList, TourDetail, TourWrite (nested), SavedTour,
                        OperatorTourList, DepartureDate
  views.py           ← All tour endpoints
  permissions.py     ← IsOperator, IsOperatorOwner
  urls.py            ← All tour URL patterns
  admin.py           ← Full admin with inlines + bulk actions
  migrations/
    0001_initial.py  ← Complete migration
  fixtures/
    initial_tours.json ← 1 live tour + departures + itinerary + stays + policy + FAQs

apps/bookings/
  models.py          ← Booking, EnquiryMessage
  serializers.py     ← BookingCreate, BookingDetail, OperatorBooking,
                        EnquiryCreate, EnquiryDetail
  views.py           ← All booking endpoints
  urls.py            ← All booking URL patterns
  admin.py           ← Full admin with bulk confirm/cancel
  migrations/
    0001_initial.py  ← Complete migration
  fixtures/
    dashboard_test.json ← 2 test bookings (confirmed + pending)

waybound/
  api_urls.py        ← Updated with all new routes
```

## Steps to apply

### 1. Copy files into your project

Replace the empty stubs with the files above:
```bash
cp apps/tours/models.py      <project>/apps/tours/models.py
cp apps/tours/serializers.py <project>/apps/tours/serializers.py
cp apps/tours/views.py       <project>/apps/tours/views.py
cp apps/tours/permissions.py <project>/apps/tours/permissions.py
cp apps/tours/urls.py        <project>/apps/tours/urls.py
cp apps/tours/admin.py       <project>/apps/tours/admin.py

cp apps/bookings/models.py      <project>/apps/bookings/models.py
cp apps/bookings/serializers.py <project>/apps/bookings/serializers.py
cp apps/bookings/views.py       <project>/apps/bookings/views.py
cp apps/bookings/urls.py        <project>/apps/bookings/urls.py
cp apps/bookings/admin.py       <project>/apps/bookings/admin.py

cp waybound/api_urls.py <project>/waybound/api_urls.py

# Copy migrations (or use makemigrations — see note below)
cp apps/tours/migrations/0001_initial.py    <project>/apps/tours/migrations/0001_initial.py
cp apps/bookings/migrations/0001_initial.py <project>/apps/bookings/migrations/0001_initial.py

# Copy fixtures
cp -r apps/tours/fixtures    <project>/apps/tours/
cp -r apps/bookings/fixtures <project>/apps/bookings/
```

### 2. Install Pillow (for ImageField)
```bash
pip install Pillow
```

### 3. Run migrations
```bash
python manage.py migrate
```

**Alternative — let Django generate migrations itself** (safer if you already
have a users migration in place):
```bash
# Delete the 0001_initial.py files we provided, then:
python manage.py makemigrations tours bookings
python manage.py migrate
```

### 4. Create an operator user (if needed)
```bash
python manage.py shell
>>> from apps.users.models import User
>>> u = User.objects.create_user('operator@test.com', 'Test1234!', role='operator',
...                               first_name='Benard', last_name='Kiprotich')
>>> u.pk  # note the pk — fixtures expect operator pk=1
```

### 5. Load fixtures
```bash
python manage.py loaddata apps/tours/fixtures/initial_tours.json
python manage.py loaddata apps/bookings/fixtures/dashboard_test.json
```

> **Note:** `initial_tours.json` expects `operator pk=1`.
> `dashboard_test.json` expects `tourist pk=2`.
> Adjust pk values in the JSON if your users have different pks.

### 6. Test key endpoints
```bash
# Health check
curl http://127.0.0.1:8000/api/v1/tours/

# Tour detail
curl http://127.0.0.1:8000/api/v1/tours/georgia-kazbegi-svaneti-trek/

# Login to get token
curl -X POST http://127.0.0.1:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@waybound.com","password":"Waybound2026!"}'

# Bookings (authenticated)
curl http://127.0.0.1:8000/api/v1/bookings/ \
  -H "Authorization: Bearer <access_token>"
```

## API reference

| Method | URL | Auth | Description |
|--------|-----|------|-------------|
| GET | `/api/v1/tours/` | None | Public tour list (filterable) |
| POST | `/api/v1/tours/` | Operator | Create tour |
| GET | `/api/v1/tours/operator/` | Operator | Own tours (all statuses) |
| GET | `/api/v1/tours/saved/` | Tourist | Saved tours |
| GET | `/api/v1/tours/<slug>/` | None | Tour detail |
| PATCH | `/api/v1/tours/<slug>/` | Operator (owner) | Edit tour |
| DELETE | `/api/v1/tours/<slug>/` | Operator (owner) | Archive tour |
| PATCH | `/api/v1/tours/<slug>/publish/` | Operator / Admin | Submit/publish |
| POST | `/api/v1/tours/<slug>/save/` | Tourist | Save tour |
| DELETE | `/api/v1/tours/<slug>/save/` | Tourist | Unsave tour |
| POST | `/api/v1/tours/<slug>/photos/` | Operator (owner) | Upload photo |
| DELETE | `/api/v1/tours/<slug>/photos/<id>/` | Operator (owner) | Delete photo |
| GET/POST | `/api/v1/bookings/` | Tourist | Own bookings / create booking |
| GET | `/api/v1/bookings/<pk>/` | Tourist / Operator | Booking detail |
| PATCH | `/api/v1/bookings/<pk>/cancel/` | Tourist | Cancel booking |
| GET | `/api/v1/bookings/operator/` | Operator | Bookings for own tours |
| PATCH | `/api/v1/bookings/<pk>/confirm/` | Operator | Confirm booking |
| GET/POST | `/api/v1/bookings/enquiries/` | Any / Operator | Private tour enquiries |

## Query parameters for GET /api/v1/tours/

| Param | Example | Description |
|-------|---------|-------------|
| `category` | `Trekking` | Filter by category |
| `country` | `Georgia` | Filter by country (partial) |
| `destination` | `Kazbegi` | Filter by destination (partial) |
| `min_price` | `50000` | Minimum price (adult) |
| `max_price` | `150000` | Maximum price (adult) |
| `min_days` | `3` | Minimum trip duration |
| `max_days` | `14` | Maximum trip duration |
| `difficulty` | `Moderate` | Filter by difficulty |
| `tour_type` | `multi` | `multi` or `single` |
| `q` | `caucasus` | Full-text search |
| `order` | `-rating` | Sort: `price_adult`, `-price_adult`, `days`, `-days`, `rating`, `-rating`, `-created_at` |
| `page` | `2` | Page number |
| `page_size` | `10` | Results per page |

## What's still needed before frontend wiring

1. **Pillow** installed (`pip install Pillow`)
2. **MEDIA_ROOT** configured to serve uploaded photos in dev
   (add to `dev.py`: `from django.conf.urls.static import static` and append
   `+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)` to urlpatterns)
3. Operator user created + fixtures loaded
4. Frontend `goToBooking()` in `booking.html` changed from localStorage-only
   to `POST /api/v1/bookings/` (Task 19 wiring)
