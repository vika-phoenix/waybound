# Waybound — Backend (Django REST API)

## Stack
- **Python 3.11+** / Django 4.2 / Django REST Framework
- **Dev DB**: SQLite (zero config)
- **Prod DB**: PostgreSQL (Hetzner)
- **Auth**: django-allauth (email+pw, Google, Apple) + JWT tokens
- **Payments**: YooKassa (Russian) + Stripe (international) — Task 15

---

## First-time setup

```bash
# 1. Clone / navigate to this folder
cd waybound_backend

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dev dependencies
pip install -r requirements-dev.txt

# 4. Create your .env file
cp .env.example .env
# Open .env and set DJANGO_SECRET_KEY to any long random string
# Leave DATABASE_URL blank (SQLite will be used automatically)

# 5. Run migrations
python manage.py migrate

# 6. Create a superuser (for /admin)
python manage.py createsuperuser

# 7. Start the dev server
python manage.py runserver
# → API available at http://127.0.0.1:8000
# → Admin at    http://127.0.0.1:8000/admin
```

---

## Verify it's working

Open these URLs in your browser or Postman:

| URL | Expected |
|-----|----------|
| `http://127.0.0.1:8000/admin/` | Django admin login page |
| `http://127.0.0.1:8000/api/v1/auth/health/` | `{"status":"ok","app":"users"}` |
| `http://127.0.0.1:8000/api/v1/tours/health/` | `{"status":"ok","app":"tours"}` |
| `http://127.0.0.1:8000/api/v1/bookings/health/` | `{"status":"ok","app":"bookings"}` |
| `http://127.0.0.1:8000/api/v1/reviews/health/` | `{"status":"ok","app":"reviews"}` |

---

## Project structure

```
waybound_backend/
│
├── manage.py
├── requirements.txt          # production deps
├── requirements-dev.txt      # + dev/debug deps
├── .env.example              # copy to .env, never commit .env
│
├── waybound/                # Django project package
│   ├── settings/
│   │   ├── base.py           # shared (all envs)
│   │   ├── dev.py            # SQLite, console email, CORS open
│   │   └── prod.py           # PostgreSQL, real email, security headers
│   ├── urls.py               # root URL conf
│   ├── api_urls.py           # all /api/v1/ routes
│   └── wsgi.py
│
└── apps/                     # one folder per domain
    ├── users/                # User model, auth endpoints (Tasks 9-12)
    ├── tours/                # Tour listings, search (Task 16)
    ├── bookings/             # Booking + payments (Task 15)
    └── reviews/              # Review submission (Task 20)
```

---

## Settings & environment

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SECRET_KEY` | ✅ | Any long random string |
| `DJANGO_DEBUG` | dev only | `True` in .env, `False` in prod |
| `DATABASE_URL` | prod only | `postgres://user:pw@host:5432/db` |
| `CORS_ALLOWED_ORIGINS` | optional | Frontend URL(s), comma-separated |

Manage.py defaults to `settings.dev`. On the server, set:
```bash
export DJANGO_SETTINGS_MODULE=waybound.settings.prod
```

---

## Task roadmap (backend)

| # | Task | Status |
|---|------|--------|
| 8 | Django setup (this file) | ✅ Done |
| 9 | email+pw auth (register / login / logout / /me) | Next |
| 10 | Google OAuth | After 9 |
| 11 | Apple OAuth | After 9 |
| 12 | Phone OTP auth | After 8 |
| 13 | Tourist sign-up → DB | After 9 |
| 14 | Sign-in → JWT + session | After 9 |
| 15 | YooKassa + Stripe payments | After 8 |
| 16 | Tour listings API | After 8 |
| 17 | Traveler dashboard page | After 14 |
| 18 | Operator dashboard page | After 14 |
| 19 | Booking confirmation emails | After 13+15 |
| 20 | Review submission | After 14 |
| 21 | Messaging | After 14 |
| 22 | Admin panel customisation | After 8 |
| 23 | SEO layer | After 16 |
