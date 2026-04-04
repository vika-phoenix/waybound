# Waybound - Technical Documentation

> Small-group adventure tour booking platform. Django REST API backend + vanilla HTML/JS frontend.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Tech Stack](#tech-stack)
3. [Project Structure](#project-structure)
4. [Backend Apps](#backend-apps)
5. [API Endpoints](#api-endpoints)
6. [Frontend Pages](#frontend-pages)
7. [Database Models](#database-models)
8. [Authentication & Authorization](#authentication--authorization)
9. [Payment Flow](#payment-flow)
10. [Booking Lifecycle](#booking-lifecycle)
11. [Cancellation & Refund Logic](#cancellation--refund-logic)
12. [Scheduled Jobs](#scheduled-jobs)
13. [Admin Panel](#admin-panel)
14. [Local Development Setup](#local-development-setup)
15. [Deploying to Production (Railway)](#deploying-to-production-railway)
16. [Git Workflow](#git-workflow)
17. [Railway Gotchas & Lessons Learned](#railway-gotchas--lessons-learned)

---

## Architecture Overview

```
Frontend (vanilla HTML/JS)          Backend (Django REST)
  +-----------------------+          +------------------------+
  | 29 HTML pages         |  ---->>  | /api/v1/               |
  | nav.js, config.js     |  JSON    | Django 4.2 + DRF       |
  | No build step needed  |          | APScheduler (bg jobs)  |
  +-----------------------+          +------------------------+
                                            |
                            +---------------+----------------+
                            |               |                |
                       PostgreSQL     Cloudflare R2     YooKassa
                       (Railway)      (media files)    (payments)
```

- **Backend**: Django 4.2 REST API on Railway, PostgreSQL, WhiteNoise for static, Cloudflare R2 for media uploads
- **Frontend**: Plain HTML/CSS/JS (no React/Vue), served separately (Cloudflare Pages or any static host)
- **Payments**: YooKassa (Russian + international cards), with CBR exchange rate conversion
- **Email**: Brevo (production), console output (local dev)
- **Scheduler**: APScheduler with DjangoJobStore for recurring background jobs
- **Live URL**: `https://waybound-production.up.railway.app`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Framework | Django 4.2.11, Django REST Framework 3.15 |
| Database | SQLite (dev), PostgreSQL (prod) |
| Auth | JWT (simplejwt), django-allauth 0.63.2[socialaccount] (OAuth) |
| Payments | YooKassa SDK 3.3 |
| Email | django-anymail + Brevo |
| Scheduler | APScheduler + django-apscheduler |
| Media storage | Cloudflare R2 via django-storages + boto3 |
| Static files | WhiteNoise |
| Admin UI | django-jazzmin |
| Hosting | Railway (backend), Cloudflare Pages (frontend) |
| Frontend | Vanilla HTML, CSS, JavaScript |

---

## Project Structure

```
main/
+-- backend/
|   +-- waybound/                  # Django project
|   |   +-- settings/
|   |   |   +-- base.py            # Shared config (apps, JWT, CORS, allauth, jazzmin)
|   |   |   +-- dev.py             # Dev: SQLite, DEBUG=True, console email
|   |   |   +-- prod.py            # Prod: PostgreSQL, Brevo, R2, security headers
|   |   +-- urls.py                # Root URL conf
|   |   +-- api_urls.py            # /api/v1/ routes
|   |   +-- wsgi.py
|   |   +-- contact_view.py        # Contact form endpoint
|   +-- apps/
|   |   +-- users/                 # Auth, profiles, verification, OTP
|   |   +-- tours/                 # Tour CRUD, departures, photos, waitlist
|   |   +-- bookings/              # Bookings, enquiries, scheduler
|   |   +-- payments/              # YooKassa initiate + webhook
|   |   +-- reviews/               # Tour reviews + moderation
|   +-- manage.py
|   +-- requirements.txt
|   +-- Procfile
|   +-- railway.toml               # Railway deploy config
|   +-- .env.example
|
+-- frontend/
|   +-- waybound.html              # Landing page
|   +-- adventures.html            # Tour browsing + filters
|   +-- tour_detail_page.html      # Single tour page + booking
|   +-- booking.html               # Checkout
|   +-- operator-dashboard.html    # Operator portal
|   +-- operator-tour-create.html  # Tour creation form
|   +-- (24 more HTML pages)
|   +-- nav.js                     # Shared navigation
|   +-- config.js                  # API base URL config
|
+-- TECHNICAL_DOC.md               # This file
+-- PROD_SETUP.md                  # Production setup, external services, roadmap
```

---

## Backend Apps

### 1. Users (`apps/users/`)

Handles authentication, user profiles, operator verification, and social OAuth.

**Key files:**
- `models.py` - User (custom, email-based), VerificationDocument, OTPCode
- `views.py` - 15 endpoints: register, login, logout, OAuth, OTP, password reset, profile
- `social_adapter.py` - Custom allauth adapter for OAuth (Google, Apple, Yandex, VK)
- `otp_service.py` - Phone OTP generation and verification
- `management/commands/create_staff_roles.py` - Creates admin Groups (Bookings Manager, Content Reviewer, Support Staff)

**User roles:**
- `tourist` - Books tours, leaves reviews, manages wishlist
- `operator` - Creates tours, manages departures, handles bookings/enquiries
- `admin` - Full Django admin access

### 2. Tours (`apps/tours/`)

Tour listings with rich content: departures, itinerary, accommodation, photos, FAQs, cancellation policy.

**Key files:**
- `models.py` - Tour (main), DepartureDate, DayItinerary, StayBlock, CancelPeriod, TourPhoto, TourFAQ, SavedTour, WaitlistEntry
- `views.py` - CRUD, filtering, photo upload, wishlist, waitlist
- `serializers.py` - Read + write serializers with nested create/update
- `emails.py` - Tour-related email templates
- `telegram.py` - Telegram notification helpers

**Tour types:**
- `multi` - Multi-day tours with fixed departure dates
- `single` - Single-day tours bookable on any date

**Tour status flow:** `draft` -> `review` -> `live` -> `paused`/`archived`

**Departure status:** `open` | `guaranteed` | `full` | `cancelled`

### 3. Bookings (`apps/bookings/`)

Booking lifecycle, enquiry system, and all scheduled background jobs.

**Key files:**
- `models.py` - Booking, EnquiryMessage, EnquiryReply
- `views.py` - Create/cancel bookings, operator confirm, enquiry threads
- `scheduler.py` - 6 background jobs (auto-cancel, reminders, auto-complete)

**Booking status flow:** `pending` -> `confirmed` -> `completed` | `cancelled` | `refunded`

### 4. Payments (`apps/payments/`)

YooKassa integration for deposits and balance payments.

**Key files:**
- `views.py` - `initiate/` (create YooKassa payment) + `webhook/` (handle payment confirmation)

**Payment methods:** `yookassa` (card), `sbp` (Russian fast payment), `bank` (bank transfer)

### 5. Reviews (`apps/reviews/`)

Tourist reviews with operator replies and admin moderation.

**Key files:**
- `models.py` - TourReview (1-5 stars, title, body, status, operator_reply)
- `views.py` - List, create, operator reply
- On save: auto-updates `tour.rating` and `tour.review_count`

**Review status flow:** `pending` -> `approved` | `rejected`

---

## API Endpoints

Base URL: `/api/v1/`

### Auth (`/api/v1/auth/`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `register/tourist/` | Tourist sign-up | No |
| POST | `register/operator/` | Operator sign-up | No |
| POST | `login/` | Email/password login -> JWT | No |
| POST | `logout/` | Blacklist refresh token | Yes |
| GET/PATCH | `me/` | Get/update profile | Yes |
| POST | `change-password/` | Change password | Yes |
| POST | `password-reset/` | Request reset email | No |
| POST | `password-reset/confirm/` | Confirm reset with token | No |
| POST | `social/token/` | OAuth JWT exchange | No |
| POST | `otp/request/` | Request phone OTP | No |
| POST | `otp/verify/` | Verify OTP -> JWT | No |
| POST | `verify/` | Upload verification doc | Operator |
| GET | `social/connections/` | List connected OAuth accounts | Yes |
| DELETE | `social/connections/<provider>/` | Disconnect OAuth | Yes |
| POST | `token/refresh/` | Refresh JWT | No |

### Tours (`/api/v1/tours/`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/` | List tours (public, filterable) | No |
| POST | `/` | Create tour | Operator |
| GET | `operator/` | My tours (operator) | Operator |
| GET | `saved/` | My saved tours | Tourist |
| GET | `<slug>/` | Tour detail | No |
| PATCH | `<slug>/` | Edit tour | Operator (owner) |
| DELETE | `<slug>/` | Archive tour | Operator (owner) |
| PATCH | `<slug>/publish/` | Submit for review / publish | Operator (owner) |
| POST/DELETE | `<slug>/save/` | Save/unsave tour | Tourist |
| POST | `<slug>/photos/` | Upload tour photo | Operator (owner) |
| DELETE | `<slug>/photos/<id>/` | Delete photo | Operator (owner) |
| POST | `<slug>/stays/<night>/photos/` | Upload stay photo | Operator (owner) |
| DELETE | `<slug>/stays/photos/<id>/` | Delete stay photo | Operator (owner) |
| POST | `<slug>/waitlist/` | Join waitlist | No |

**Tour list filters:** category, difficulty, country, tour_type, status, search, ordering, date range

### Bookings (`/api/v1/bookings/`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/` | My bookings | Tourist |
| GET | `<pk>/` | Booking detail | Tourist/Operator |
| POST | `<pk>/cancel/` | Cancel booking | Tourist |
| POST | `<pk>/cancel-preview/` | Preview refund amount | Tourist |
| GET | `operator/` | Bookings for my tours | Operator |
| POST | `<pk>/confirm/` | Confirm booking | Operator |
| POST | `<pk>/message/` | Message tourist | Operator |
| GET | `enquiries/` | Enquiries for my tours | Operator |
| GET | `enquiries/mine/` | My enquiries | Tourist |
| POST | `enquiries/<pk>/reply/` | Reply to enquiry | Operator |
| POST | `enquiries/<pk>/tourist-reply/` | Follow-up on enquiry | Tourist |
| POST | `enquiries/<pk>/read/` | Mark enquiry as read | Operator |

### Payments (`/api/v1/payments/`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `initiate/` | Start YooKassa payment | Tourist |
| POST | `webhook/` | YooKassa callback | No (HMAC verified) |

### Reviews (`/api/v1/reviews/`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/` | Approved reviews (public) | No |
| GET | `mine/` | My reviews | Tourist |
| GET | `operator/` | Reviews for my tours | Operator |
| POST | `<pk>/reply/` | Reply to review | Operator |

### Other

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health/` | Health check |
| POST | `/api/v1/contact/` | Contact form |
| GET | `/admin/` | Django admin panel |

---

## Frontend Pages

Every page has an English version and a Russian (`_ru.html`) counterpart. The Russian pages are separate files — not server-rendered — with translated UI text and client-side translation maps for DB-sourced values.

### Public Pages

| English | Russian | Purpose |
|---------|---------|---------|
| `waybound.html` | `waybound_ru.html` | Landing page - hero, featured tours, trust badges, CTA |
| `adventures.html` | `adventures_ru.html` | Tour search + filter (destination, category, difficulty, price, duration, guaranteed, dates) |
| `tour_detail_page.html` | `tour_detail_page_ru.html` | Tour detail: itinerary, stays, photos, map, reviews, departure picker, booking form |
| `about.html` | `about_ru.html` | Company story + photo gallery (lightbox on click) |
| `how-it-works.html` | `how-it-works_ru.html` | Platform explainer (search -> book -> travel) |
| `help.html` | `help_ru.html` | FAQ & help center (8 sections, 35 questions, live search) |
| `contact.html` | `contact_ru.html` | Contact form |
| `reviews.html` | `reviews_ru.html` | Browse all approved reviews |
| `small-group-benefits.html` | `small-group-benefits_ru.html` | Why small groups (max 15 people) |
| `operator.html` | `operator_ru.html` | Operator onboarding landing page |
| `rewards.html` | `rewards_ru.html` | Rewards program info |

### Auth Pages

| English | Russian | Purpose |
|---------|---------|---------|
| `signin.html` | `signin_ru.html` | Login (email + Google/Apple/Yandex/VK OAuth) |
| `signup.html` | `signup_ru.html` | Tourist registration |
| `signup-operator.html` | `signup-operator_ru.html` | Operator registration + ID upload |
| `reset-password.html` | `reset-password_ru.html` | Password reset flow |

### Tourist Dashboard

| English | Russian | Purpose |
|---------|---------|---------|
| `my-bookings.html` | `my-bookings_ru.html` | View bookings, pay balance, cancel, leave review |
| `my-reviews.html` | `my-reviews_ru.html` | View submitted reviews |
| `my-messages.html` | `my-messages_ru.html` | Enquiry conversations |
| `saved-tours.html` | `saved-tours_ru.html` | Wishlist |
| `settings.html` | `settings_ru.html` | Profile, password, preferences |
| `booking.html` | `booking_ru.html` | Checkout page (pre-payment) |
| `booking-confirmation.html` | `booking-confirmation_ru.html` | Post-booking confirmation |

### Operator Dashboard

| English | Russian | Purpose |
|---------|---------|---------|
| `operator-dashboard.html` | `operator-dashboard_ru.html` | Full portal: bookings, enquiries, tours, stats |
| `operator-tour-create.html` | `operator-tour-create_ru.html` | Create/edit tour: all fields, departures, itinerary, stays, photos, FAQs, cancel policy |

### Legal

| English | Russian | Purpose |
|---------|---------|---------|
| `terms.html` | `terms_ru.html` | Terms of service (tourists) |
| `terms-experts.html` | `terms-experts_ru.html` | Terms for operators/experts |
| `privacy.html` | `privacy_ru.html` | Privacy policy |
| `trust-safety.html` | `trust-safety_ru.html` | Trust & safety: guarantees, cooling-off, cancellation |

### Configuration

| File | Purpose |
|------|---------|
| `nav.js` | Shared navigation component (injected into all pages) — language-aware, detects `_ru.html` pages and renders Russian labels + correct `_ru.html` hrefs |
| `config.js` | API base URL - change this when switching between local and prod |
| `404.html` | Error page |

---

## Database Models

### Users

```
User
  - email (unique, login identifier)
  - role: tourist | operator | admin
  - first_name, last_name, phone, country, bio
  - avatar (image)
  - is_verified (operator verification status)
  - email_verified, phone_verified
  - marketing_emails, telegram_chat_id
  - experience_years (operator)
  - payout_name, payout_bank, payout_account, payout_bik, payout_corr_account

  Computed via serializer (read-only):
  - has_password: False for OAuth-only accounts (no usable password set)
    Used by settings page to show "Set password" instead of "Change password"

VerificationDocument
  - user -> User (FK, multiple docs per user)
  - doc_type: identity | credential
  - status: pending | approved | rejected
  - submitted_at, original_name

OTPCode
  - phone, code, created_at, used
```

### Tours

```
Tour
  - operator -> User
  - title, slug (unique), status: draft|review|live|paused|archived
  - category, categories (multi-select JSON), difficulty, tour_type: multi|single
  - country, destination, region, lat/lng, timezone
  - days (1-60), price_adult, price_child (default 85% of adult), currency
  - max_group (max 15), min_group, deposit_pct (0-100%), balance_due_days
  - description (HTML), highlights, includes, excludes, requirements
  - meeting_point, meeting_time, end_point
  - language, languages (multi-select), difficulty_note, extras (JSON)
  - rating, review_count, booking_count (denormalized)

DepartureDate
  - tour -> Tour
  - start_date, end_date, spots_total, spots_left
  - status: open | guaranteed | full | cancelled
  - price_override, notes

DayItinerary       (day_number, title, description, meals, elevation)
StayBlock          (property_name, type, comfort_level, night_from/to, room_types)
PropertyPhoto      (stay -> StayBlock, image, order, caption)
CancelPeriod       (days_before_min/max, penalty_pct, label)
TourPhoto          (image, order, caption - hero photo = order 0)
TourFAQ            (question, answer, order)
SavedTour          (tourist -> User, tour -> Tour)
WaitlistEntry      (tour, email, departure_label)
```

### Bookings

```
Booking
  - tourist -> User (nullable for guest), tour -> Tour, departure -> DepartureDate
  - reference: TRP-XXXXXX (auto-generated)
  - status: pending | confirmed | completed | cancelled | refunded
  - adults, children, infants
  - first_name, last_name, email, phone, country
  - emergency_name, emergency_phone, notes
  - room_preference, selected_extras
  - cancel_policy_snapshot (JSON - frozen at booking time)
  - departure_date
  - price_adult, price_child, total_price, extras_cost, room_supplement_cost
  - deposit_paid, deposit_status: pending|paid|failed
  - balance_due_date, balance_paid, balance_status
  - payment_method: yookassa|sbp|bank
  - refund_amount, refund_status: none|pending|issued|manual
  - cooling_off_until (datetime - penalty-free cancel window)
  - created_at, confirmed_at, cancelled_at

EnquiryMessage
  - tour -> Tour, sender -> User (nullable)
  - name, email, preferred_from/to, adults, children, infants, message
  - read_by_operator, operator_reply, replied_at

EnquiryReply
  - enquiry -> EnquiryMessage, sender -> User
  - text, is_from_operator
```

### Reviews

```
TourReview
  - tour -> Tour, booking -> Booking (optional), tourist -> User
  - rating (1-5), title, body
  - operator_reply, replied_at
  - status: pending | approved | rejected
  - unique_together: (tourist, tour)
```

---

## Authentication & Authorization

### JWT Flow
1. User logs in via `/auth/login/` or `/auth/social/token/`
2. Backend returns `access` (60 min) + `refresh` (30 days) tokens
3. Frontend sends `Authorization: Bearer <access>` on every API call
4. On 401, frontend calls `/auth/token/refresh/` with the refresh token
5. Logout blacklists the refresh token

### `change-password` endpoint

`current_password` is optional. If the user has no usable password (`has_usable_password() = False`, i.e. OAuth-only account), the backend skips the current-password check and allows setting a new password directly. After setting a password, the user can disconnect social accounts.

### `social/connections/<provider>/` DELETE

Uses `provider__iexact` (case-insensitive) for the DB lookup because allauth stores provider names in title case (`'Yandex'`, `'Google'`) but the frontend passes lowercase. Blocks disconnect if the user has no usable password and no other social accounts (would lock them out).

---

### OAuth Providers
- **Google** - Standard OAuth2 (consent screen must be set to "External" in Google Cloud Console)
- **Apple** - Disabled (requires $99/yr Apple Developer account — commented out in `INSTALLED_APPS`)
- **Yandex** - Yandex ID (primary for Russian users)
- **VK** - VKontakte (for Russian users)

**OAuth flow (JWT-embedded redirect):**
1. Frontend calls `/accounts/<provider>/login/?process=login` (or `?process=login&connect=1` to link to existing account)
2. allauth handles provider redirect and callback
3. Custom `AccountAdapter._jwt_redirect()` in `social_adapter.py` mints JWT tokens and embeds them directly in the redirect URL as query params (`social_access`, `social_refresh`, `social_user`)
4. Browser lands on `signin.html?social_access=...` — frontend reads tokens from URL, stores in `localStorage`, cleans up URL
5. No cookie exchange needed — works cross-origin without `SameSite=None` cookies

**Language routing after OAuth:** `signin_ru.html` and `signup_ru.html` store `sessionStorage.waybound_oauth_lang = 'ru'` before the OAuth redirect. `signin.html` reads this on landing and routes to Russian pages (`waybound_ru.html`, `settings_ru.html`, etc.).

**Connecting a provider to an existing account:** Uses `connect=1` param. `pre_social_login` stores `wb_connect=1` in the session; `get_login_redirect_url` detects this and redirects back to `settings.html?social_access=...` instead of `signin.html`.

**`/auth/social/token/` endpoint** — legacy session-based fallback, no longer the primary flow.

### Staff Roles (Django Groups)

| Role | Bookings | Tours | Users | Reviews | Enquiries |
|------|----------|-------|-------|---------|-----------|
| Bookings Manager | View + Edit | View | View | - | View + Edit |
| Content Reviewer | View | Full CRUD | - | View + Edit | - |
| Support Staff | View | View | View | View | View + Edit |

Created via: `python manage.py create_staff_roles` (runs automatically on every deploy)

---

## Payment Flow

```
Tourist clicks "Book Now"
        |
        v
Frontend -> POST /bookings/ (create booking, status=pending)
        |
        v
Frontend -> POST /payments/initiate/ { booking_id, payment_type: "deposit" }
        |
        v
Backend creates YooKassa Payment (converts to RUB via CBR rate if needed)
        |
        v
Backend returns { payment_id, confirmation_url }
        |
        v
Frontend embeds YooKassa payment iframe/redirects
        |
        v
Tourist pays -> YooKassa sends webhook -> POST /payments/webhook/
        |
        v
Backend updates booking.deposit_paid, deposit_status='paid'
If deposit >= total_price: balance_status='paid' too
        |
        v
Operator confirms booking -> status='confirmed'
        |
        v
(Later) Tourist pays balance via same flow with payment_type="balance"
```

**Deposit calculation:** The deposit is the higher of:
- Tour's base `deposit_pct` (operator-configurable, 0-100%)
- Current cancellation penalty percentage (protects operator for last-minute bookings)

**Currency:** All YooKassa payments are in RUB. If tour is priced in another currency, the backend fetches the CBR daily exchange rate and converts.

---

## Booking Lifecycle

```
                    +-- Tourist doesn't pay deposit within 24h --> auto-cancel
                    |
[PENDING] ----------+-- Tourist pays deposit
                    |
                    +-- Operator doesn't confirm within 48h --> auto-cancel + refund
                    |
                    v
[CONFIRMED] --------+-- Tourist cancels --> refund per policy --> [CANCELLED]
                    |
                    +-- Operator cancels --> full refund (platform rule) --> [REFUNDED]
                    |
                    +-- Tour ends + 24h --> [COMPLETED]
                                               |
                                               v
                                        Review reminder (5 days later)
```

---

## Cancellation & Refund Logic

### Platform rules (non-negotiable)

1. **Cooling-off window:** Every booking gets a penalty-free cancellation window:
   - 30 minutes if departure is >7 days away
   - 15 minutes if departure is <=7 days away

2. **Operator cancels = full refund:** If the operator cancels a confirmed booking, tourist gets 100% back. No exceptions.

### Default cancellation tiers (operator can customize)

| Days before departure | Penalty | Refund |
|---|---|---|
| 30+ days | 0% | 100% |
| 14-29 days | 50% | 50% |
| 0-13 days | 100% | 0% |

Operators can set stricter or more generous tiers. The policy is snapshotted into `booking.cancel_policy_snapshot` at booking time so later changes don't affect existing bookings.

---

## Scheduled Jobs

All jobs run via APScheduler with DjangoJobStore (persisted to database). The scheduler starts once via `--preload` in gunicorn.

| Job | Frequency | What it does |
|-----|-----------|-------------|
| `auto_cancel_expired_bookings` | Hourly | Cancel bookings with no deposit after 24h; cancel unconfirmed bookings after 48h; cancel past-departure PENDING bookings |
| `auto_complete_bookings` | Every 6h | Mark CONFIRMED bookings as COMPLETED 24h after tour ends; send review request email |
| `send_review_reminders` | Daily | Follow-up review reminder 5 days after completion if no review submitted |
| `send_deposit_reminders` | Hourly | Remind tourist at 12h and 22h after booking if deposit not paid |
| `send_balance_reminders` | Daily | Remind tourist 14/7/3 days before balance due date |
| `send_operator_balance_reminders` | Every 6h | Notify operators about unpaid balances with adaptive frequency (weekly -> every 3 days -> daily based on proximity to penalty escalation) |

---

## Admin Panel

URL: `/admin/` - Powered by django-jazzmin (AdminLTE3 theme)

### Registered models and actions

**Users:**
- User - full CRUD, role filtering
- VerificationDocument - approve/reject actions with email notifications
- OTPCode - view/filter

**Tours:**
- Tour - inline editors for departures, itinerary, stays, cancellation periods, photos, FAQs
- Actions: publish, pause, reject, delete_safe
- SavedTour - list display

**Bookings:**
- Booking - list + filter by status/currency/payment, actions: confirm, mark_completed
- EnquiryMessage - mark as read

**Reviews:**
- TourReview - actions: approve, reject

**Auth:**
- Groups (staff roles)

**APScheduler:**
- DjangoJob, DjangoJobExecution (view scheduled job status)

---

## Local Development Setup

### Prerequisites
- Python 3.11+
- Git

### First-time setup

```bash
# 1. Clone
git clone https://github.com/vika-phoenix/waybound.git
cd waybound

# 2. Backend setup
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Environment
cp .env.example .env
# Edit .env - set DJANGO_SECRET_KEY to any long random string
# Everything else has sensible defaults for local dev

# 4. Database
python manage.py migrate

# 5. Create admin user
python manage.py createsuperuser

# 6. Create staff roles
python manage.py create_staff_roles

# 7. (Optional) Load sample data
python manage.py loaddata apps/tours/fixtures/initial_tours.json

# 8. Run server
python manage.py runserver
# API at http://localhost:8000/api/v1/
# Admin at http://localhost:8000/admin/
```

### Frontend setup

```bash
# From project root
cd frontend

# Option 1: VS Code Live Server (right-click waybound.html -> Open with Live Server)
# Option 2: Python HTTP server
python -m http.server 5500

# Edit config.js to point API_BASE to your backend:
# const API_BASE = 'http://localhost:8000/api/v1';
```

### Settings

- **Local dev** uses `waybound.settings.dev` automatically (SQLite, DEBUG=True, console email)
- **Production** uses `waybound.settings.prod` (PostgreSQL, Brevo, R2, security headers)
- Settings are split: `base.py` (shared) -> imported by `dev.py` or `prod.py`

### Key local dev notes

- Emails print to terminal (console backend) — no real email sending
- SQLite database stored at `backend/db.sqlite3`
- Media uploads go to `backend/media/`
- No need for R2, Brevo, or YooKassa for basic local testing
- YooKassa test mode works with test shop ID/secret from .env.example
- OAuth won't work locally without provider credentials
- Changes to `base.py` affect both local and prod — be careful
- Changes to `prod.py` only affect Railway — safe to change locally
- Changes to `dev.py` only affect local — safe to change

---

## Deploying to Production (Railway)

### How it works

Every `git push` to `main` triggers automatic deployment on Railway. The start command in `railway.toml` runs:

```
DJANGO_SETTINGS_MODULE=prod -> migrate -> collectstatic -> create_staff_roles -> gunicorn (--preload)
```

### Pushing changes

**Always run from the project root** (`c:\Users\deadv\Downloads\tour_pj\main`), NOT from `backend/`:

```bash
cd c:\Users\deadv\Downloads\tour_pj\main
git add backend/path/to/file.py
git commit -m "description of change"
git push
```

If you run `git add` from inside `backend/`, you need paths relative to `backend/` (no `backend/` prefix). This is confusing — just always run from the project root.

### After pushing

1. Go to Railway dashboard — the deploy starts automatically
2. Watch the **Deploy logs** (not Build logs)
3. Wait for the healthcheck to pass (up to 5 minutes)
4. If it fails, check the deploy logs for the actual error

### Creating a superuser

Since Railway shell doesn't always have Python available, add these **Variables** in Railway temporarily:

```
DJANGO_SUPERUSER_EMAIL    = admin@waybound.com
DJANGO_SUPERUSER_PASSWORD = your-secure-password
```

Then change the start command in `railway.toml` to include:
```
... && python manage.py createsuperuser --no-input --email $DJANGO_SUPERUSER_EMAIL || true && gunicorn ...
```

Push, deploy, verify login works at `/admin/`, then remove the createsuperuser line and push again.

---

## Git Workflow

### Structure
- Git root is `main/` (the project root)
- Backend code is in `backend/`
- Frontend code is in `frontend/`
- Always run git commands from the project root

### Pushing changes
```bash
cd c:\Users\deadv\Downloads\tour_pj\main

# Stage specific files
git add backend/apps/tours/models.py frontend/adventures.html

# Or stage all changes in a directory
git add backend/apps/

# Commit and push
git commit -m "description"
git push
```

### What NOT to commit
- `.env` files (already in .gitignore)
- `db.sqlite3` (already in .gitignore)
- `__pycache__/` (already in .gitignore)
- API keys, secrets, passwords

### If migrations get corrupted on Railway
1. Delete all migration files locally: `find apps -path "*/migrations/*.py" -not -name "__init__.py" -delete`
2. Regenerate: `python manage.py makemigrations users tours bookings reviews payments`
3. Test locally: `rm db.sqlite3 && python manage.py migrate`
4. Delete PostgreSQL in Railway and recreate it
5. Push the new migrations

---

## Railway Gotchas & Lessons Learned

These are real issues encountered during deployment. Reference this before debugging.

### 1. ALLOWED_HOSTS must include `localhost`
Railway's healthcheck pings from inside the container using `localhost`. Without it, Django returns 400 and healthcheck fails forever.
```
DJANGO_ALLOWED_HOSTS = .railway.app,localhost
```

### 2. SECURE_SSL_REDIRECT must be False
Railway handles SSL at the proxy level. If Django also redirects to HTTPS, you get an infinite redirect loop (browser shows blank page, curl shows "too many redirections").
```python
SECURE_SSL_REDIRECT = False  # in prod.py
```

### 3. CSRF_TRUSTED_ORIGINS is required
Without it, Django admin login returns 403 Forbidden. Must include the full Railway URL with protocol:
```python
CSRF_TRUSTED_ORIGINS = ['https://waybound-production.up.railway.app']
```

### 4. SECURE_PROXY_SSL_HEADER is required
Railway terminates SSL at the proxy. Django needs to trust the `X-Forwarded-Proto` header to know the original request was HTTPS:
```python
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

### 5. Domain port must match gunicorn's port
Gunicorn binds to `$PORT` (Railway assigns this, usually 8080). When generating a domain in Railway -> Settings -> Networking, set the target port to `8080`. Check the deploy logs for the actual port:
```
[INFO] Listening at: http://0.0.0.0:8080
```

### 6. DATABASE_URL — do NOT set manually
Railway auto-injects this from the PostgreSQL service. Setting it manually (even blank) breaks things.

### 7. Environment variables with no default crash the app
Any `config('KEY')` without `default=''` in base.py will crash on Railway if that variable isn't set. Always add defaults for optional keys:
```python
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')
```

### 8. MEDIA_URL must end with a slash
If `R2_PUBLIC_URL` is empty or missing the trailing `/`, Django throws `urls.E006`. The prod.py handles this automatically now.

### 9. Squash migrations before first deploy
Don't deploy with 30+ incremental migrations — partial failures create tables without recording the migration, leading to "table already exists" / "table does not exist" whack-a-mole. Squash into clean initials first.

### 10. Use `--preload` with gunicorn
Without `--preload`, each gunicorn worker independently boots Django and starts the scheduler. This causes duplicate scheduler job warnings in the logs. With `--preload`, Django boots once in the master process, then workers fork from it.

### 11. Railway shell may not have Python
`python` and `python3` may not be in PATH. If you need a shell command, add it to the start command in `railway.toml` instead:
```
... && python manage.py some_command || true && gunicorn ...
```
The `|| true` ensures the deploy continues even if the command fails (e.g., superuser already exists).

### 12. Deploy logs vs Database logs
In Railway, make sure you're looking at the **Django service** logs, not the **PostgreSQL service** logs. PostgreSQL logs show checkpoint and replication info, not your app errors.

---

## Russian Localisation

### Architecture

- Every page has a `_ru.html` counterpart (e.g. `adventures_ru.html`).
- These are static files — not server-rendered. Russian text is hardcoded in HTML and JS.
- DB-sourced values (difficulty, categories, languages, country) are always stored in **English** in the database. Russian pages translate them **client-side** at render time using JS translation maps.
- When Russian pages submit form data to the backend, reverse maps convert Russian display values back to English before the API call.

### nav.js language detection

`nav.js` exports `_navIsRuPage()` which checks if the current page filename ends in `_ru.html`. The shared `buildDropdown()` function uses this to render menu labels (Дашборд / Dashboard, etc.) and route all hrefs to the correct `_ru.html` or `.html` file.

### Client-side translation maps (Russian pages)

These maps live inside the `_ru.html` files and **must not** be modified by a translation script:

**`tour_detail_page_ru.html`**
- `diffTranslate` — English difficulty → Russian display (`'Moderate' → 'Средне'`)
- `catTranslate` — English category → Russian display
- `langNameMap` — language code/name → Russian display
- `_enToRuCountry` — English country name → Russian display

**`operator-tour-create_ru.html`**
- `ruToEn` (categories) — Russian display → English for backend submission
- `ruToEn` (difficulty) — Russian display → English for backend submission
- `_ruToEnC` (countries) — Russian display → English for backend submission
- `COUNTRY_TIMEZONES` keys — must remain in Russian to match the Russian datalist options

### Backend fix: tour pause/unpause (`backend/apps/tours/views.py`)

`TourWriteSerializer` does not expose the `status` field, so a `PATCH {status: 'paused'}` was silently ignored. Fixed by intercepting status-only PATCH requests **before** the serializer runs:

```python
if set(request.data.keys()) == {'status'}:
    # Only allows: live→paused and paused→live
    OPERATOR_STATUS_TRANSITIONS = {
        'paused': (Tour.Status.LIVE,   Tour.Status.PAUSED),
        'live':   (Tour.Status.PAUSED, Tour.Status.LIVE),
    }
    ...
    tour.status = target
    tour.save(update_fields=['status'])
    return Response(TourDetailSerializer(tour, context={'request': request}).data)
```

### Known translation script corruption patterns

When running an automated translation script on `_ru.html` files, watch for these failure modes:

| Pattern | What goes wrong | Safe value |
|---------|----------------|------------|
| `t.status === 'live'` | Script translates `'live'` → `'активный'` — breaks status comparisons | Must stay `'live'`, `'paused'`, `'draft'` etc. |
| `'\u26A0'` | Script adds `;` → `'\u26A0;'` renders as literal text "⚠;" | No semicolon |
| `'style-card ' + s.cls` | Script strips the space → CSS class names merge, layout breaks | Space before `+` is required |
| `' id="checklist...'` | Script strips leading space and/or closing `"` from string variables | Space + closing quote required |
| Values inside `ruToEn` / `_ruToEnC` maps | Right-hand English values get translated to Russian — then form submissions send Russian to the backend | Right-hand side of reverse maps must stay in English |
| `COUNTRY_TIMEZONES['Russia']` | Key gets translated to `'Россия'` in English page, or left as `'Russia'` in Russian page where datalist uses Russian — must match the datalist | Keys must match the datalist options language |

### Russian grammatical declension

Plurals in Russian follow three forms (1 / 2-4 / 5+). Key patterns used across pages:

| Concept | 1 | 2-4 | 5+ |
|---------|---|-----|----|
| Adult | взрослый | взрослых | взрослых |
| Child | ребёнок | ребёнка | детей |
| Day | день | дня | дней |
| Minute | минуту | минуты | минут |
| Hour | час | часа | часов |
| Booking | бронирование | бронирования | бронирований |
| Message | сообщение | сообщения | сообщений |
| Unread | непрочитанное | непрочитанных | непрочитанных |

### Summary of fixed bugs (by file)

**`backend/apps/tours/views.py`**
- Pause/unpause tour status-only PATCH now works via pre-serializer interception

**`frontend/nav.js`**
- `buildDropdown()` is language-aware — renders Russian labels and `_ru.html` hrefs on Russian pages
- Bell notification click routes to `operator-dashboard_ru.html` on Russian pages

**`frontend/waybound_ru.html`**
- Fixed `'style-card' + s.cls` → `'style-card ' + s.cls` (missing space broke homepage layout)
- Fixed style card clicks to route to `adventures_ru.html?cat=`

**`frontend/operator-dashboard_ru.html`**
- Fixed `'\u26A0;'` → `'\u26A0'` (warning icon was rendering as literal "⚠;")
- Fixed `doneAttr`/`actionAttr`/`icoAttr` string variables (missing space + closing quote caused `id` attributes to merge with adjacent text)
- Fixed checklist action links to point to `settings_ru.html#...`
- Fixed status labels to Russian (published/draft/review/paused/archived)
- Fixed `t.status === 'активный'` → `t.status === 'live'` (translation script had corrupted this)
- Fixed price/day, time-ago, spots, booking count, guest count, pax strings to Russian with correct declensions
- Fixed messages header to Russian with declensions

**`frontend/operator-tour-create_ru.html`**
- Fixed Requirements + organiser note placeholders to Russian
- Fixed "X photos added" → "X фото добавлено"
- Fixed country datalist to Russian names
- Fixed `COUNTRY_TIMEZONES` key to match Russian datalist
- Added `ruToEn` category + difficulty maps in restore-from-edit code (old tours had Russian category names stored in DB from before the fix — map corrects them on load)
- Added `_ruToEnC` country map in `collectFormData` so backend always receives English country

**`frontend/tour_detail_page.html`** and **`frontend/tour_detail_page_ru.html`**
- Private request modal: date + message are now required fields with red border highlight on empty submission
- Russian version has same validation plus Russian pax declensions in submit
- Added client-side translation maps for difficulty, categories, languages, country (Russian page)

**`frontend/adventures.html`** and **`frontend/adventures_ru.html`**
- Removed "Private tours only" filter toggle (private tours are direct-link only, not browsable)

**`frontend/booking.html`** and **`frontend/booking_ru.html`**
- Name/email/phone now prefill from `waybound_user` localStorage on page load
- Fixed "Change date / Изменить дату" link to route back to correct tour detail page
- Russian page: `paxTxt` uses Russian declensions; back-to-tour link uses `tour_detail_page_ru.html`

**`frontend/signup-operator_ru.html`**
- Fixed placeholder text for company name, languages, certificates to Russian
- Fixed "Wellness / Йога" label (was partially English)

**`frontend/about.html`** and **`frontend/about_ru.html`**
- Community photo gallery: clicking a photo now opens a lightbox modal (fade-in overlay, full image, close with ✕ or Escape or click backdrop)

**`frontend/terms-experts_ru.html`**
- Translated all remaining English sections: Bookings, Payment Agent, Service Fees, Booking Terms, Taxes, Conduct, Content, Disclaimers, Liability, Indemnification, Governing Law, Dispute Resolution, contact block, and footer
