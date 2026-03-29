# Waybound - Production Setup & Roadmap

> Everything needed to go live, plus what to tackle next.

---

## Table of Contents

1. [Production Architecture](#production-architecture)
2. [Railway Deployment](#railway-deployment)
3. [External Services Setup](#external-services-setup)
4. [Environment Variables Reference](#environment-variables-reference)
5. [Post-Deploy Checklist](#post-deploy-checklist)
6. [Services That Can't Be Tested Locally](#services-that-cant-be-tested-locally)
7. [Frontend / UI Polish (Do Later)](#frontend--ui-polish-do-later)
8. [Features for Later (Once You Have More Tourists)](#features-for-later-once-you-have-more-tourists)
9. [Known Limitations](#known-limitations)

---

## Production Architecture

```
                  Cloudflare Pages
                  (frontend HTML)
                        |
                        v
Users  ------>   Railway (backend)
                  Django + Gunicorn
                  WhiteNoise (static)
                        |
             +----------+----------+
             |          |          |
        PostgreSQL   Cloudflare   External
        (Railway)    R2 (media)   Services
                                     |
                          +----------+----------+
                          |          |          |
                        Brevo    YooKassa    OAuth
                        (email)  (payments)  Providers
```

| Service | Purpose | Cost |
|---------|---------|------|
| Railway | Backend hosting + PostgreSQL | $5/mo hobby plan |
| Cloudflare Pages | Frontend hosting | Free |
| Cloudflare R2 | Media storage (tour photos, avatars, docs) | Free (10GB + 10M reads/mo) |
| Brevo | Transactional email | Free (300 emails/day) |
| YooKassa | Payment processing (RUB) | Per-transaction fees |
| Domain (optional) | Custom domain | ~$10-15/year |

---

## Railway Deployment

### Initial setup

1. Push code to GitHub (repo: `vika-phoenix/waybound`)
2. Go to **railway.app** -> Login with GitHub
3. **New Project** -> Deploy from GitHub -> select `waybound`
4. Set **root directory** to `backend`
5. Add **PostgreSQL**: + New -> Database -> PostgreSQL
6. Add environment variables (see [reference below](#environment-variables-reference))
7. Deploy

### How deploys work

Every `git push` to `main` triggers automatic deployment. The start command in `railway.toml` runs:

```
migrate -> collectstatic -> create_staff_roles -> gunicorn
```

### After first successful deploy

1. Generate domain: Service -> Settings -> Networking -> Generate Domain
2. Update `DJANGO_ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` with real domain
3. Create superuser via Railway shell:
   ```
   /root/.nix-profile/bin/python3 manage.py createsuperuser
   ```
4. Load sample tour data (optional):
   ```
   /root/.nix-profile/bin/python3 manage.py loaddata apps/tours/fixtures/initial_tours.json
   ```

### Troubleshooting

- **Build fails**: Check that root directory is `backend`
- **Health check fails**: Check Deploy logs (not Build logs) for the real error
- **Migration conflicts**: Delete PostgreSQL service, recreate, redeploy
- **Missing env var crash**: Add the variable in Railway Variables tab with empty value if not needed yet
- **Shell commands**: Python path on Railway is `/root/.nix-profile/bin/python3`, not `python`

---

## External Services Setup

### 1. Cloudflare R2 (Media Storage)

Stores tour photos, avatars, verification documents, stay photos.

**Setup:**
1. Sign up at **cloudflare.com** (free)
2. Left sidebar -> **R2** -> Create bucket -> name: `waybound-media`
3. Bucket Settings -> Public Access -> enable "R2.dev subdomain"
   - Copy the public URL: `https://pub-xxxxxxxxxxxx.r2.dev/`
4. R2 -> Manage R2 API Tokens -> Create token:
   - Permissions: Object Read & Write
   - Bucket: `waybound-media` only
   - Copy Access Key ID + Secret Access Key
5. Note your Account ID from the R2 overview page
   - Endpoint URL: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`

**Env vars to set:**
```
R2_ACCESS_KEY_ID     = (from step 4)
R2_SECRET_ACCESS_KEY = (from step 4)
R2_BUCKET_NAME       = waybound-media
R2_ENDPOINT_URL      = https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_PUBLIC_URL        = https://pub-xxxxxxxxxxxx.r2.dev/
```

### 2. Brevo (Transactional Email)

Sends booking confirmations, deposit reminders, balance reminders, review requests, password resets, enquiry notifications.

**Setup:**
1. Sign up at **brevo.com** (free - 300 emails/day)
2. Top-right menu -> SMTP & API -> API Keys tab
3. Generate new API key -> copy it
4. Senders & IPs -> Senders -> Add sender
   - For testing: use your Gmail address as sender
   - For production: add `noreply@yourdomain.com` and verify DNS (DKIM/SPF)

**Env vars to set:**
```
BREVO_API_KEY      = xkeysib-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEFAULT_FROM_EMAIL = Waybound <noreply@yourdomain.com>
```

**Emails the platform sends:**
| Trigger | Recipient | Email |
|---------|-----------|-------|
| Booking created | Tourist | Booking confirmation + deposit instructions |
| Booking created | Operator | New booking notification |
| Booking confirmed | Tourist | Confirmation with tour details |
| Booking cancelled | Tourist | Cancellation + refund details |
| Booking cancelled | Operator | Cancellation notification |
| Deposit not paid (12h) | Tourist | First deposit reminder |
| Deposit not paid (22h) | Tourist | Final deposit warning |
| Balance due (14/7/3 days) | Tourist | Balance payment reminder |
| Balance unpaid | Operator | Balance reminder (adaptive) |
| Tour completed | Tourist | Review request |
| Review not submitted (5d) | Tourist | Review follow-up |
| Enquiry received | Operator | New enquiry notification |
| Enquiry replied | Tourist | Operator reply notification |
| Password reset | User | Reset link |
| Operator verified | Operator | Approval notification |

### 3. YooKassa (Payments)

Russian payment gateway. Handles card payments (Visa, Mastercard, Mir), SBP (fast bank transfers).

**Setup:**
1. Register at **yookassa.ru** (requires Russian legal entity or IP/self-employed)
2. Create a shop in the dashboard
3. Get Shop ID and Secret Key
4. Set up webhook URL: `https://your-domain.railway.app/api/v1/payments/webhook/`
   - Event: `payment.succeeded`
5. For testing: use test shop credentials (provided by YooKassa)

**Env vars to set:**
```
YOOKASSA_SHOP_ID    = (your shop ID)
YOOKASSA_SECRET_KEY = (your secret key)
```

**How it works:**
- All payments processed in RUB
- If tour is priced in another currency, backend converts using CBR daily exchange rate
- Deposits: percentage of total (configurable per tour, 0-100%)
- Balance: remaining amount, due N days before departure

### 4. Google OAuth

**Setup:**
1. Go to **console.cloud.google.com**
2. Create project -> APIs & Services -> Credentials -> Create OAuth 2.0 Client
3. Authorized redirect URI: `https://your-domain.railway.app/accounts/google/login/callback/`
4. Copy Client ID and Secret

**Env vars:**
```
GOOGLE_CLIENT_ID     = (from Google Cloud Console)
GOOGLE_CLIENT_SECRET = (from Google Cloud Console)
```

### 5. Apple Sign In

**Setup:**
1. Requires Apple Developer Account ($99/year)
2. Register App ID with "Sign in with Apple" capability
3. Create Services ID for web authentication
4. Create Key for Sign in with Apple
5. Redirect URI: `https://your-domain.railway.app/accounts/apple/login/callback/`

**Env vars:**
```
APPLE_CLIENT_ID    = (Services ID)
APPLE_TEAM_ID      = (Team ID)
APPLE_KEY_ID       = (Key ID)
APPLE_PRIVATE_KEY  = (private key contents)
```

### 6. Yandex OAuth

**Setup:**
1. Go to **oauth.yandex.ru** -> Create app
2. Permissions: login:email, login:info
3. Redirect URI: `https://your-domain.railway.app/accounts/yandex/login/callback/`

**Env vars:**
```
YANDEX_CLIENT_ID     = (from Yandex)
YANDEX_CLIENT_SECRET = (from Yandex)
```

### 7. VK OAuth

**Setup:**
1. Go to **dev.vk.com** -> My Apps -> Create
2. Platform: Web
3. Redirect URI: `https://your-domain.railway.app/accounts/vk/login/callback/`

**Env vars:**
```
VK_CLIENT_ID     = (from VK)
VK_CLIENT_SECRET = (from VK)
```

### 8. Telegram Bot (Operator Notifications)

**Setup:**
1. Message @BotFather on Telegram -> `/newbot`
2. Name it "Waybound Notifications" (or similar)
3. Copy the bot token

**Env vars:**
```
TELEGRAM_BOT_TOKEN = (from BotFather)
```

**Current status:** Bot token field exists, `telegram.py` helper file exists in tours app. Operators can save their `telegram_chat_id` in their profile. Actual notification sending is prepared but not fully wired into all events yet.

### 9. Cloudflare Pages (Frontend Hosting)

**Setup:**
1. Go to **pages.cloudflare.com** -> Connect to Git
2. Select `waybound` repo
3. Build settings:
   - Root directory: `frontend`
   - Build command: (leave empty - no build needed)
   - Output directory: `frontend`
4. Deploy

Your frontend gets a free `*.pages.dev` domain. You can add a custom domain later.

**Important:** Update `config.js` in the frontend to point to your Railway backend URL:
```javascript
const API_BASE = 'https://your-backend.railway.app/api/v1';
```

---

## Environment Variables Reference

### Required for deploy (app won't start without these)

| Variable | Example | Notes |
|----------|---------|-------|
| `DJANGO_SETTINGS_MODULE` | `waybound.settings.prod` | Always this value |
| `DJANGO_SECRET_KEY` | `a8f3k...long-random-string` | Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DJANGO_ALLOWED_HOSTS` | `.railway.app` | Leading dot = wildcard |
| `DATABASE_URL` | (auto-injected by Railway) | Do NOT set manually |

### Required for features to work

| Variable | Feature |
|----------|---------|
| `BREVO_API_KEY` | All email sending |
| `YOOKASSA_SHOP_ID` + `YOOKASSA_SECRET_KEY` | Payment processing |
| `R2_ACCESS_KEY_ID` + `R2_SECRET_ACCESS_KEY` + `R2_BUCKET_NAME` + `R2_ENDPOINT_URL` + `R2_PUBLIC_URL` | Photo/file uploads |
| `CORS_ALLOWED_ORIGINS` | Frontend accessing API (set to frontend domain) |
| `FRONTEND_URL` | Email links back to frontend |

### Optional (features work without them, just disabled)

| Variable | Feature |
|----------|---------|
| `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` | Google login |
| `APPLE_CLIENT_ID` + `APPLE_TEAM_ID` + `APPLE_KEY_ID` + `APPLE_PRIVATE_KEY` | Apple login |
| `YANDEX_CLIENT_ID` + `YANDEX_CLIENT_SECRET` | Yandex login |
| `VK_CLIENT_ID` + `VK_CLIENT_SECRET` | VK login |
| `TELEGRAM_BOT_TOKEN` | Telegram notifications |
| `ANTHROPIC_API_KEY` | AI features (if any) |
| `DEFAULT_FROM_EMAIL` | Defaults to `noreply@waybound.com` |
| `ADMIN_NOTIFICATION_EMAIL` | Admin alert recipient |

---

## Post-Deploy Checklist

- [ ] Backend is live and `/api/v1/health/` returns `{"status": "ok"}`
- [ ] Django admin accessible at `/admin/`
- [ ] Superuser created
- [ ] Staff roles created (auto-runs on deploy via start command)
- [ ] Frontend deployed on Cloudflare Pages
- [ ] `config.js` updated with backend URL
- [ ] Brevo API key set -> test email sending (create a booking)
- [ ] R2 bucket created -> test photo upload (create a tour with photos)
- [ ] YooKassa credentials set -> test payment (create test booking)
- [ ] CORS_ALLOWED_ORIGINS set to frontend domain
- [ ] FRONTEND_URL set to frontend domain (for email links)
- [ ] Custom domain configured (optional)
- [ ] OAuth providers configured (optional, per-provider)
- [ ] Sample tours loaded or first real tour created

---

## Services That Can't Be Tested Locally

These require external accounts and real credentials. They either silently no-op or fail locally without setup.

| Service | What happens locally without it | How to test |
|---------|--------------------------------|-------------|
| **Brevo email** | Emails print to terminal (console backend) | Works fine locally - just read terminal output |
| **Cloudflare R2** | Files saved to `backend/media/` locally | Works fine locally - just uses disk storage |
| **YooKassa payments** | Payment initiation will fail (no credentials) | Use YooKassa test mode with test shop ID |
| **Google OAuth** | "Sign in with Google" button won't work | Need Google Cloud project + OAuth credentials |
| **Apple OAuth** | "Sign in with Apple" button won't work | Need Apple Developer account ($99/yr) |
| **Yandex OAuth** | "Sign in with Yandex" button won't work | Need Yandex OAuth app |
| **VK OAuth** | "Sign in with VK" button won't work | Need VK developer app |
| **Telegram notifications** | Silent no-op (no bot token) | Need Telegram bot via @BotFather |
| **PostgreSQL** | Uses SQLite locally (auto) | Works fine locally |
| **WhiteNoise** | Not used locally (Django serves static in debug) | Works fine locally |
| **Custom domain + HTTPS** | Localhost is HTTP | Only on production |

**Bottom line:** Email, media uploads, and basic functionality all work locally out of the box. Only payments and OAuth need external credentials to test.

---

## Frontend / UI Polish (Do Later)

These are design and UX improvements that don't affect core functionality. Do them whenever you have time.

### Visual improvements
- [ ] Responsive design audit - test all 29 pages on mobile/tablet
- [ ] Dark mode toggle (CSS variables are already structured for this)
- [ ] Loading skeletons instead of blank screens while API calls load
- [ ] Image lazy loading on tour listing cards
- [ ] Tour photo gallery with lightbox (currently just grid)
- [ ] Animated transitions between pages (currently hard navigations)
- [ ] Better error states (API down, network error, 500) - currently just alerts

### Tour discovery
- [ ] Map view for adventures page (currently list only)
- [ ] Tour comparison feature (compare 2-3 tours side by side)
- [ ] "Similar tours" section on tour detail page
- [ ] Recently viewed tours (localStorage)
- [ ] Share tour via WhatsApp/Telegram/Copy link

### Booking flow
- [ ] Multi-step booking form with progress indicator
- [ ] Booking summary sidebar that scrolls with the page
- [ ] Better date picker for departure selection
- [ ] Guest count selector with +/- buttons (currently plain inputs)

### Operator dashboard
- [ ] Charts/graphs for booking trends (monthly, by tour)
- [ ] Calendar view for departures
- [ ] Drag-and-drop photo reordering
- [ ] Tour preview before publishing
- [ ] Bulk departure date creation (e.g., "every Saturday in July")

### General
- [ ] Favicons and meta tags for social sharing (OG tags)
- [ ] SEO: proper meta descriptions on all pages
- [ ] Accessibility audit (ARIA labels, keyboard navigation, contrast)
- [ ] Performance: minify CSS/JS, optimize images
- [ ] Cookie consent banner (required for EU users)
- [ ] Language switcher (Russian/English) if targeting both markets

---

## Features for Later (Once You Have More Tourists)

These are features that make sense only once you have real traffic and data. Building them now would be premature.

### Growth & engagement
- [ ] **Referral program** - Tourist refers friend, both get discount (rewards.html exists but isn't wired to backend)
- [ ] **Loyalty points / credits** - Earn points per booking, redeem on future tours
- [ ] **Promo codes** - Operator or platform-wide discount codes
- [ ] **Gift cards** - Buy a Waybound gift card for someone
- [ ] **Push notifications** - Browser push for booking updates, new tours in saved destinations
- [ ] **Newsletter** - Weekly "new tours" email digest to opted-in tourists

### Discovery & trust
- [ ] **Tour recommendations** - "Because you booked X, you might like Y" (needs booking history data)
- [ ] **Trending tours** - Show tours with most bookings this month
- [ ] **Verified reviews badge** - Show "Verified booking" on reviews from actual bookers
- [ ] **Review photos** - Let tourists upload photos with their review
- [ ] **Q&A on tour page** - Public questions and operator answers (vs current private enquiry system)
- [ ] **Blog / travel guides** - SEO content for organic traffic

### Operator tools
- [ ] **Dynamic pricing** - Surge pricing for popular dates, discounts for low-fill departures
- [ ] **Early bird discounts** - Auto-apply discount if booked N+ days in advance
- [ ] **Last-minute deals** - Auto-discount tours departing within 7 days with empty spots
- [ ] **Multi-operator support** - Multiple guides per tour (co-hosting)
- [ ] **Revenue analytics** - Monthly/quarterly earnings reports, tax export
- [ ] **Payout management** - Track commission deductions, pending payouts

### Platform operations
- [ ] **Dispute resolution** - Tourist opens dispute, admin mediates (currently manual via email)
- [ ] **Automated payouts** - Scheduled operator payouts after tour completion (currently manual)
- [ ] **Fraud detection** - Flag suspicious bookings (multiple cancellations, payment failures)
- [ ] **A/B testing** - Test different tour card layouts, booking flows
- [ ] **Analytics dashboard** - Admin view of platform-wide metrics (GMV, conversion rate, etc.)
- [ ] **Mobile app** - React Native or Flutter (once web is proven)

### Scaling
- [ ] **Multi-currency display** - Show prices in tourist's local currency (backend already converts to RUB for payment, but frontend could show EUR/USD estimates)
- [ ] **Multi-language** - Russian + English at minimum, plus tour-specific language content
- [ ] **CDN for images** - Cloudflare CDN in front of R2 (currently R2 direct - fine for now)
- [ ] **Redis caching** - Cache tour listings, popular queries (premature until traffic warrants it)
- [ ] **Search engine** - Elasticsearch/Meilisearch for better tour search (current Django ORM filtering is fine for <1000 tours)

---

## Known Limitations

| Area | Limitation | Impact |
|------|-----------|--------|
| Payments | YooKassa only (Russian gateway) | International tourists may have issues with non-Russian cards |
| Currency | All payments in RUB | Tourist sees tour price in original currency but pays in RUB at CBR rate |
| Frontend | No build system | No minification, no tree-shaking, no TypeScript - acceptable for current scale |
| Frontend | No framework | All vanilla JS - harder to maintain as complexity grows |
| Email | 300/day Brevo free tier | Enough for early stage; upgrade when needed ($9/mo for 5000/mo) |
| File storage | 10GB R2 free tier | Enough for ~2000 tour photos; upgrade when needed |
| OAuth | Apple requires $99/yr dev account | Can skip Apple login initially |
| Telegram | Not fully wired into all events | Token + helper exists but not all notification triggers are connected |
| Mobile | Responsive but no native app | Mobile web works, native app can come later |
| Countries | 4 countries (Russia, Georgia, Turkey, Armenia) | Limited by current operators; expand as operators join |
| Tours | Max 15 people per group | Platform design choice, not a bug |
| Search | Basic Django ORM filtering | Fine for <1000 tours; consider Meilisearch later |
