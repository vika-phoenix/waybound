# WAYBOUND — FULL PROJECT HANDOFF
# Generated for Claude Code transfer
# ============================================================

## WHAT THIS IS
Tour booking marketplace. Operators list tours, tourists browse and book.
Django REST backend + plain HTML/CSS/JS frontend (no React, no build step).
Russian market primary (YooKassa payments, RUB currency), Stripe for international.

## TECH STACK
- Backend: Django 4.x, DRF, SimpleJWT, SQLite (dev) / PostgreSQL (prod)
- Frontend: Vanilla HTML/CSS/JS, no framework, no bundler
- Auth: JWT (access 60min, refresh 30 days)
- Storage: local /media/ in dev
- Python: 3.12, Windows dev machine (PowerShell)

## FOLDER STRUCTURE
waybound_backend/
  manage.py
  apps/
    users/         — custom User model (role: tourist|operator|admin)
    tours/         — Tour, DepartureDate, DayItinerary, StayBlock,
                     CancelPeriod, TourPhoto, TourFAQ, SavedTour
    bookings/      — Booking, EnquiryMessage
    reviews/       — stub only, not implemented yet
  waybound/
    settings/base.py, dev.py, prod.py
    api_urls.py    — all /api/v1/ routes
    urls.py

frontend/ (flat HTML files, served directly or via Django static)
  waybound.html         — homepage
  adventures.html        — tour listing/search
  tour_detail_page.html  — tour detail + booking widget
  booking.html           — booking form
  booking-confirmation.html
  operator.html          — "List a tour" landing page
  operator-dashboard.html — operator dashboard (My tours, Bookings, Earnings)
  operator-tour-create.html — create/edit tour form
  signup-operator.html   — 3-step operator application
  signin.html / signup.html
  settings.html
  my-bookings.html / saved-tours.html / my-reviews.html

## API BASE URL
http://127.0.0.1:8000/api/v1/

## ALL ENDPOINTS

### Auth (apps/users/)
POST   /auth/register/tourist/       — { email, password, password2, first_name, last_name }
POST   /auth/register/operator/      — { email, password, password2, first_name, last_name, phone, country, company_name }
POST   /auth/login/                  — { email, password } → { access, refresh, user }
POST   /auth/logout/
GET    /auth/me/                     — current user profile
PATCH  /auth/me/                     — update profile (T17 remnant — NOT WIRED)
POST   /auth/change-password/        — { old_password, new_password } (NOT WIRED)
POST   /auth/token/refresh/          — { refresh } → { access }

### Tours — Public
GET    /tours/                       — list live tours
       ?category=Trekking&country=Georgia&q=search
       &min_price=&max_price=&min_days=&max_days=
       &difficulty=&order=-created_at
       → { count, results: [TourListSerializer] }
GET    /tours/<slug>/                — full tour detail → TourDetailSerializer

### Tours — Operator (JWT + role=operator)
GET    /tours/operator/              — operator's own tours (all statuses)
POST   /tours/                       — create tour (nested JSON)
PATCH  /tours/<slug>/                — edit tour
DELETE /tours/<slug>/                — archive tour (status→archived)
PATCH  /tours/<slug>/publish/        — operator: draft→review | admin: review→live
POST   /tours/<slug>/photos/         — multipart: file=<img>, order=<int>, caption=<str>
DELETE /tours/<slug>/photos/<id>/    — delete photo

### Tours — Tourist (JWT)
GET    /tours/saved/                 — wishlist
POST   /tours/<slug>/save/           — save tour
DELETE /tours/<slug>/save/           — unsave

### Bookings — Tourist (JWT)
GET    /bookings/                    — own bookings
POST   /bookings/                    — create booking
       { tour_slug, adults, children, infants,
         first_name, last_name, email, phone, country,
         departure_date, notes, emergency_name, emergency_phone }
       Price calculated server-side. Returns { reference: "TRP-XXXXXX", ... }
GET    /bookings/<pk>/               — booking detail
PATCH  /bookings/<pk>/cancel/        — cancel booking

### Bookings — Operator (JWT + role=operator)
GET    /bookings/operator/           — all bookings for operator's tours
PATCH  /bookings/<pk>/confirm/       — confirm pending booking

### Enquiries (public POST, operator GET)
POST   /bookings/enquiries/          — private tour request (no auth needed)
       { tour_slug, name, email, adults, children, infants,
         preferred_from, preferred_to, message }
GET    /bookings/enquiries/          — operator: see enquiries for own tours

## KEY MODELS

### User (apps/users/models.py)
role: tourist | operator | admin
Fields: email(unique), phone, first_name, last_name, avatar, bio, country
        is_staff, email_verified, phone_verified

### Tour (apps/tours/models.py)
operator → FK User(role=operator)
status: draft | review | live | paused | archived
Fields: title, slug(auto), category, difficulty, tour_type(multi|single)
        country, destination, region, lat/lng
        days, price_adult, price_child(default 85% of adult), currency, max_group, min_group
        description(HTML), highlights[], includes[], excludes[], tags[]
        requirements, meeting_point, end_point, emoji
        rating, review_count, booking_count (denormalised)

Related: departures(DepartureDate), itinerary(DayItinerary), stays(StayBlock)
         cancel_policy(CancelPeriod), photos(TourPhoto order=0 is hero), faqs(TourFAQ)

### Booking (apps/bookings/models.py)
tourist → FK User (nullable for guest)
tour → FK Tour (PROTECT)
departure → FK DepartureDate (nullable for single-day)
status: pending | confirmed | completed | cancelled | refunded
reference: "TRP-XXXXXX" (auto-generated)
Fields: adults, children, infants
        first_name, last_name, email, phone, country
        departure_date, notes, emergency_name, emergency_phone
        price_adult, price_child, total_price, deposit_paid, currency
        payment_ref, payment_method(yookassa|stripe|bank)
Business logic: confirm→spots_left decrements; cancel→spots_left restores

### EnquiryMessage (apps/bookings/models.py)
Private tour request from modal. One-way for now (Task 21 adds replies).
Fields: tour, sender(nullable), name, email
        preferred_from/to, adults, children, infants, message, read_by_operator

## FRONTEND KEY VARIABLES (localStorage)
waybound_access     — JWT access token
waybound_refresh    — JWT refresh token
waybound_user       — JSON { email, first_name, last_name, role, ... }
waybound_saved      — array of saved tour slugs
waybound_last_booking — last booking data
waybound_draft_tour — operator tour creation draft
waybound_enquiries  — private tour enquiries (pre-Task 21 fallback)
waybound_booking_return — URL to return to after login

## API CONSTANTS IN FRONTEND
var BOOKING_API = 'http://127.0.0.1:8000/api/v1';   // booking.html
var TOUR_API    = 'http://127.0.0.1:8000/api/v1';   // operator-tour-create.html
var ACCT_API    = 'http://127.0.0.1:8000/api/v1';   // operator-dashboard.html
var TOURS_API   = 'http://127.0.0.1:8000/api/v1/tours/';  // tour_detail_page.html

## AUTH PATTERN (used in every API call)
function ah() {
  var h = { 'Content-Type': 'application/json' };
  var t = localStorage.getItem('waybound_access');
  if (t) h['Authorization'] = 'Bearer ' + t;
  return h;
}

## TEST USERS
operator@waybound.com / Waybound2026!  (pk=1, role=operator, is_staff=True)
test@waybound.com     / Waybound2026!  (pk=2, role=tourist)

## THEME SYSTEM
6 themes: ocean(default), warm, ivory, gold, forest, terra
CSS vars: --ink, --paper, --white, --ac, --ad, --mu, --ln
          --ha-bg, --ha-bd, --ha-tx (hover-a)
          --hb-bg, --hb-bd, --hb-tx (hover-b)
          --df (display font), --bf (body font)
Stored in localStorage as 'waybound-theme'

## WHAT IS WORKING (tested end-to-end)
✓ Tourist registration + login
✓ Operator registration (3-step signup-operator.html → API)
✓ Tour listing from API (adventures.html)
✓ Tour detail page loads from API (text fields update correctly)
✓ Booking form → POST /api/v1/bookings/ → confirmation page
✓ Operator dashboard loads real tours + bookings from API
✓ Operator: create tour (POST) + submit for review (PATCH /publish/)
✓ Operator: confirm/cancel bookings from dashboard
✓ Save/unsave tours (wishlist)
✓ Private tour enquiry modal → localStorage (API ready, not wired)
✓ Photo upload in tour create form
✓ Admin can approve tours via Django admin (status → live)

## KNOWN REMAINING BUGS (as of handoff)
1. tour_detail_page.html — some hardcoded content (route, exertion dots)
   may still show default values briefly before API loads
   FIX: All elements now have IDs and patchPage() sets them.
   Verify by viewing ?slug=opoo with backend running.

2. operator-dashboard.html — My tours card image layout
   Hero image should fill 160px top of card, object-fit:cover
   FIX: .tc-hero CSS applied. Verify visually.

3. operator-tour-create.html — edit mode
   When clicking Edit on a tour, form should load fields from API.
   Photos should show existing uploaded images.
   FIX: init() fetches from API when _editSlug present.
   Verify: edit an existing tour and check photos appear.

4. adventures.html — should show real hero photo not emoji
   FIX: heroPhoto: t.hero_photo_url mapped in data, used in card template.
   Verify: tours with uploaded photos should show photos on card grid.

## REMAINING TASKS

### T17 remnant — Settings page (SMALL, ~1 day)
- PATCH /api/v1/auth/me/ — update name, bio, phone, country
- POST /api/v1/auth/change-password/
- Avatar upload (multipart)
- Wire settings.html to these endpoints
- The backend endpoints exist, just need frontend wiring

### T19 — Payments (LARGE, ~1 week)
- YooKassa integration (Russian market, primary)
  POST to YooKassa API on booking creation
  Handle webhook: payment.succeeded → booking.status = confirmed
- Stripe integration (international)
- Deposit logic: 30% due at booking, 70% due 14 days before departure
- booking-confirmation.html: show payment instructions / redirect to gateway
- Refund on cancellation based on CancelPeriod tiers
- Room type supplements (tourist picks single/twin, price adjusts)
- New model fields needed: yookassa_payment_id, stripe_payment_intent_id

### T20 — Reviews (MEDIUM, ~3 days)
- Review model (stub in apps/reviews/ — needs full implementation)
  Fields: booking(FK), tour(FK), tourist(FK), rating(1-5), text, reply, created_at
- POST /api/v1/reviews/ — tourist submits after booking.status = completed
- GET /api/v1/reviews/?tour=<slug> — public review list on tour detail
- Operator reply: PATCH /api/v1/reviews/<pk>/reply/
- Update tour.rating and tour.review_count after each review (signal or in serializer)
- my-reviews.html — full implementation (list, edit, delete own reviews)
- tour_detail_page.html — load and display real reviews (currently hardcoded)

### T21 — Messaging (MEDIUM, ~3 days)
- EnquiryMessage model is built (one-way)
- Add reply threading: OperatorReply model or messages[] on EnquiryMessage
- Wire private tour enquiry modal → POST /api/v1/bookings/enquiries/
  (currently saves to localStorage as fallback)
- Operator dashboard: unread enquiry badge + enquiries tab
- Mark as read: PATCH /api/v1/bookings/enquiries/<pk>/read/
- Eventually: in-app messaging thread per booking

### T22 — Admin panel (SMALL, ~2 days)
- Custom Django admin dashboard
- Tour approval queue (tours in status=review appear with Approve/Reject buttons)
- Operator verification workflow (passport upload, credential check)
- Bulk actions already in tours/admin.py (publish, pause)
- Revenue reports by operator/month

### T23 — SEO (SMALL, ~1 day)
- Meta tags, Open Graph, Twitter cards on all pages
- sitemap.xml generation (Django sitemap framework)
- JSON-LD structured data on tour_detail_page.html
  (TouristTrip schema → eligible for Google rich results)
- Canonical URLs
- robots.txt

## PRIORITY ORDER
1. T17 remnant — quick win, operators need profiles before launch
2. T20 Reviews — high trust impact, tourists need reviews to book
3. T21 Messaging — needed for private tour enquiry flow
4. T19 Payments — biggest task, blocks real money but also most complex
5. T22 Admin — needed before real operator onboarding at scale
6. T23 SEO — last, needed at public launch

## PRODUCTION DEPLOYMENT CHECKLIST

### 1. Domain & DNS
- Buy domain (e.g. waybound.com)
- Point A record to your server IP (Render/Railway/VPS)
- After email service is set up, add SPF + DKIM DNS records (your email provider gives you these)

### 2. Environment variables (.env in prod)
Set all of these before first deploy:

```
SECRET_KEY=<generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DEBUG=False
ALLOWED_HOSTS=waybound.com,www.waybound.com

DATABASE_URL=postgres://user:pass@host:5432/dbname

FRONTEND_URL=https://waybound.com

# Email (pick one provider below)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DEFAULT_FROM_EMAIL=noreply@waybound.com
EMAIL_HOST=smtp.mailgun.org          # or smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=postmaster@waybound.com
EMAIL_HOST_PASSWORD=<your smtp password>
EMAIL_USE_TLS=True
```

### 3. Email service — pick one
| Option | Cost | Notes |
|---|---|---|
| **Mailgun** | Free up to 1000/mo | Recommended. Add domain, get SMTP creds + DNS records |
| **SendGrid** | Free up to 100/day | Similar setup |
| **Gmail SMTP** | Free | 500/day limit, fine for early stage. Use App Password |

> Once you have a provider, they give you SPF/DKIM DNS records → add to domain → emails won't land in spam.

### 4. Database
- Switch from SQLite to PostgreSQL
- On Render: add a Postgres service, copy the `DATABASE_URL`
- Run `python manage.py migrate` after first deploy

### 5. Static & media files
- Static files (CSS/JS): run `python manage.py collectstatic` — Render does this automatically if configured
- Media files (tour photos, avatars): local `/media/` works on a single server but is lost on redeploy
  - For production: configure S3-compatible storage (AWS S3, Cloudflare R2, Backblaze B2)
  - Install `django-storages` + `boto3`, set `DEFAULT_FILE_STORAGE` in prod settings
  - Until then: photos will be lost on each redeploy — acceptable for early testing, not for live

### 6. CORS & HTTPS
- Update `CORS_ALLOWED_ORIGINS` in settings to include `https://waybound.com`
- Update `CSRF_TRUSTED_ORIGINS` similarly
- Ensure all frontend `API_V1` constants use `https://` not `http://`
  - Files to update: `nav.js`, `my-messages.html`, `operator-dashboard.html`, `booking.html`, `operator-tour-create.html`, `tour_detail_page.html`

### 7. Security settings (already in prod.py, verify)
```python
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
```

### 8. JWT token lifetimes (review before launch)
Currently: access=60min, refresh=30 days. Fine for launch; shorten if needed.

### 9. Run checklist before going live
```bash
python manage.py check --deploy   # Django security check
python manage.py migrate
python manage.py collectstatic --noinput
```

### 10. Things that can wait (but needed before scale)
- Payments: YooKassa + Stripe (T19) — no real money flows until this is done
- Admin panel (T22) — use Django /admin/ for now
- CDN for static files (Cloudflare free tier is fine)

---

## HOW TO START A SESSION IN CLAUDE CODE
cd waybound_backend
claude

# First prompt to give Claude Code:
"Read apps/tours/models.py, apps/tours/views.py, and apps/tours/serializers.py.
Then run the server and test GET /api/v1/tours/ — tell me what comes back."

# To fix a visual bug:
"Open frontend/tour_detail_page.html?slug=opoo in a browser.
Tell me exactly what text you see in the difficulty section before the API loads."
