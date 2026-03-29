# WAYBOUND — FIXES & NEW ITEMS (V3)
# Only NEW items from this session. Do not mix with V2 or previous lists.
# Items marked [PERSISTS] were attempted before and not fixed — try again carefully.
# Read WAYBOUND_HANDOFF.md first for architecture context.
# ============================================================

---

## SETUP NOTES FOR CLAUDE CODE (read before starting)

### Email setup (required for contact form, report listing, private tour enquiry)
Add to .env:
  EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend   ← use this for local testing
  EMAIL_HOST=smtp.gmail.com
  EMAIL_PORT=587
  EMAIL_USE_TLS=True
  EMAIL_HOST_USER=your.gmail@gmail.com
  EMAIL_HOST_PASSWORD=your_app_password   ← Gmail App Password, not regular password
  DEFAULT_FROM_EMAIL=your.gmail@gmail.com
For local dev: console backend prints emails to runserver terminal — no real sending needed.
For production: switch to smtp backend with real Gmail App Password.
Add to settings/base.py: read all EMAIL_* vars from decouple config().

### Google OAuth setup
Check .env for GOOGLE_CLIENT_ID. If empty, Google login button must be hidden.
If setting up: Google Console → Credentials → OAuth 2.0 Client → add
  http://127.0.0.1:8000/accounts/google/login/callback/ as redirect URI.
Works on localhost without ngrok.

### Apple OAuth
Requires paid Apple Developer account ($99/year). If not set up, hide Apple button.
Do not show broken OAuth buttons to users — check credentials exist before showing.

---

## GROUP 1 — OPERATOR LANDING PAGE (operator.html)

### 1.1 [PERSISTS] Remove extra sign up links and How it works from nav
Nav on operator.html must contain: logo only + Sign in button (for returning operators).
Remove: "How it works", "Apply as a guide", any other links.
When logged in as operator: show avatar dropdown with "Go to dashboard" — no sign in, no apply.

### 1.2 [PERSISTS] When signed in as operator — show Go to dashboard, not Apply as guide
If waybound_user in localStorage has role=operator:
- Show avatar with initials (or photo)
- Dropdown first item: "Go to dashboard" → operator-dashboard.html
- Hide: "Apply as a guide", "Sign in / Sign up" buttons entirely
This must work on operator.html specifically (was broken last attempt).

### 1.3 List a tour navbar — must match site-wide nav
operator.html is missing the standard site navbar entirely or has a different/broken one.
Fix: operator.html must use the same navbar as waybound.html, adventures.html, tour_detail_page.html.
Standard nav links: Adventures | How it works | About | Help | Contact
Plus on the right: Sign in / Sign up button (when not logged in) OR avatar dropdown (when logged in).
When logged in as operator: avatar dropdown first item is "Go to dashboard".
Check the other pages to see the exact nav HTML structure and replicate it on operator.html.

---

## GROUP 2 — OPERATOR SIGNUP (signup-operator.html)

### 2.1 [PERSISTS] Multi-step tabs — content must replace not stack
This was attempted before and not fixed. Core requirement:
- Step 1 content visible on load. Steps 2 and 3 are display:none.
- Clicking Next hides current step content and shows next step content.
- Steps do NOT stack. Only one step visible at any time.
- Back button on steps 2 and 3 — goes back and re-shows previous step.
- Step indicator bar at top reflects current step with active state.
Fix goStep(n): set all .op-panel display:none, then set panel n display:block.

### 2.2 [PERSISTS] Mandatory asterisk fields not blocking Next
Required fields marked * must be validated before Next advances.
If any required field is empty or invalid: highlight red, inline error below field, stay on current step.
Step 1 required: first name, last name, email (valid format), password (min 8 chars).
Step 2 required: at least one category/tour type selected.
Step 3 required: all consent checkboxes ticked before Submit button activates.
Do NOT show browser alert() — use inline messages only.

### 2.3 Remove 50-character minimum on bio field
"Describe your tours & experience" field has no minimum length requirement.
Remove any character count validation on this field.

### 2.4 Google / Apple sign in buttons — hide if credentials not set up
Check if GOOGLE_CLIENT_ID exists and is non-empty in Django settings.
If not set: hide the Google sign in button entirely (not greyed out — hidden).
Same for Apple — hide if Apple credentials not configured.
These buttons cannot be tested locally without credentials. Do not show broken buttons.

---

## GROUP 3 — SETTINGS PAGE (settings.html)

### 3.1 [PERSISTS] Profile photo upload not working
Wire avatar file input to PATCH /api/v1/auth/me/ as multipart/form-data.
Backend: add parser_classes = [MultiPartParser, FormParser] to me() view.
Include avatar in UserMeSerializer (read: return full URL; write: accept file).
After successful upload:
  - Update waybound_user.photo_url in localStorage
  - Show uploaded photo in the settings page avatar preview immediately
  - Show uploaded photo in the nav avatar on ALL pages (nav JS reads photo_url from localStorage)

### 3.2 [PERSISTS] Remove photo option broken
"Remove photo" button: PATCH /api/v1/auth/me/ with avatar set to null/empty.
After removal: clear photo_url from localStorage waybound_user, nav reverts to initials.

### 3.3 [PERSISTS] Nav avatar — initials and photo broken on all pages except dashboard
Nav dropdown shows broken icon or "OA" on settings page and all other pages.
Root cause: malformed Unicode escape in nav dropdown HTML string.
Fix: find the dashboard icon in the nav dropdown builder — replace \u1F4CA with 📊
or correct escape \uD83D\uDCCA. Apply fix to settings.html nav JS block.
After fix: test on settings, adventures, tour detail, homepage — avatar must show
correctly with initials when no photo, photo when uploaded.

---

## GROUP 4 — OPERATOR DASHBOARD (operator-dashboard.html)

### 4.1 [PERSISTS] Dashboard icon broken in dropdown on all non-dashboard pages
Same Unicode escape bug as 3.3 above. Fix in every page that has the nav IIFE.
Pages affected: settings.html, adventures.html, tour_detail_page.html, waybound.html,
operator.html, booking.html — any page with the nav user state IIFE.
Strategy: fix the escape sequence once, then copy the corrected nav IIFE to all pages.

### 4.2 [PERSISTS] Operator signed in — all pages must show dashboard not sign in
When localStorage waybound_user.role === 'operator', every page nav must:
- Hide Sign in / Sign up button
- Hide Apply as guide button
- Show avatar with correct initials or photo
- Show dropdown with "Operator dashboard" as first item
This is broken on every page except operator-dashboard.html itself.
Fix the nav IIFE in all page files. Test each one after fixing.

### 4.3 Archive filter — hidden by default
In My tours tab, archived tours are hidden by default.
The status filter dropdown has: All statuses | Live | Draft | In review | Paused | Archived
Selecting "Archived" shows archived tours. "All statuses" does NOT include archived.
Archived tours are thus only visible when explicitly filtered for.

### 4.4 Pause tour — what it means
Pause = hide from public listings temporarily, no new bookings accepted.
Existing confirmed bookings remain valid and must still be honoured.
Operator can unpause at any time to restore to live.
Status flow: live → paused → live (reversible).
In My tours card for a paused tour: show "Unpause" button alongside Edit.
In public list API: paused tours excluded (same as draft/review).

### 4.5 Admin unable to delete tour — fix Django admin action
In Django admin (apps/tours/admin.py), the delete action must work.
Current behaviour: admin tries to delete tour, fails.
Fix: if tour has no bookings → hard delete allowed.
If tour has confirmed future bookings → block deletion, show admin a message listing the bookings.
Add a custom admin action "Delete (if no active bookings)" that checks before deleting.

### 4.6 My tours — draft tours can be hard deleted
In My tours tab, tours with status=draft or status=review (not yet live, no bookings possible)
show a "Delete" option (not "Archive"). This hard deletes the tour record entirely.
Tours with status=live, paused, or archived show "Archive" not "Delete".
Confirmation dialog before any delete: "This cannot be undone. Delete this draft?"

### 4.7 Archive tour — graceful handling
When operator archives a live or paused tour:
- Check for confirmed bookings with future departure dates
- If found: show modal listing those bookings. "You have X active bookings. Please cancel them before archiving."
- If none: archive immediately, show confirmation "Tour archived. It is no longer visible to travellers."
- Archived tour remains visible in My tours only when "Archived" filter is selected (see 4.3)

---

## GROUP 5 — NEW TOUR PAGE (operator-tour-create.html)

### 5.1 [PERSISTS] Start from previous tour — no close/X button
The "Start from a template" row must NOT have an X or close button.
Show it as a persistent collapsed one-line row at the top:
  "Start from a template: [dropdown] [Apply]"
If dismissed, it cannot be found again — so don't allow dismissal.
Hide the row only if operator has no previous tours (fetch /api/v1/tours/operator/ on load).

### 5.2 [PERSISTS] Save draft + Submit for review — move to left panel
Remove both buttons from the bottom of the main content area.
Place them in a separate styled box (bordered card) in the LEFT PANEL, below the Photos section nav link.
Box contains:
  - Auto-save status text ("✓ Saved" or "Saved locally (offline)")
  - "Save draft" ghost button
  - "Submit for review" primary button
  - After first save: "Preview" button appears (same tab, ?from=operator)
  - After first save: "← My tours" persistent link appears

### 5.3 [PERSISTS] Breadcrumb trail + go back
Add breadcrumb at top of main content area:
  Dashboard > My tours > New tour   (or > Edit tour when editing)
"Dashboard" links to operator-dashboard.html
"My tours" links to operator-dashboard.html?tab=tours
Current page label is plain text (not a link).
This updates to show "Edit tour" when ?slug= param is present.

### 5.4 Photo minimum — warning only, 1 hero required to submit
Change the "You need at least 7 photos" notice from a hard requirement to a tip/warning.
Text: "Tours with more photos get significantly more bookings. Aim for 7+."
Hard requirement for submit: at least 1 hero photo uploaded (not 7).
If no photos at all on submit: highlight photo section, scroll to it, show:
"At least one hero photo is required to submit for review."

### 5.5 Check all mandatory asterisk fields
Audit every field in the form marked with *. Confirm the submit validation checks each one.
Fields that must be mandatory for Submit (not save):
  Tour name *, Category (at least 1) *, Country *, Meeting point *, Price per person *, Max group size *, At least 1 photo
All others are optional. Fields currently marked * but not validated must either be validated or have * removed.

### 5.6 Preview opens in same tab — not new window
Preview button must use window.location.href not window.open().
Opens tour_detail_page.html?slug=<slug>&from=operator in same tab.

---

## GROUP 6 — TOUR DETAIL PAGE (tour_detail_page.html)

### 6.1 [PERSISTS] Default hardcoded values must be cleared
Before API loads, these elements must show blank/neutral values, not Kenya safari demo data:
- Rating: show "—" or 0.0, not hardcoded stars
- Review count: show "0 reviews", not a hardcoded number
- Number of days: show "—" until API responds
- Language tag: hidden until API provides language data
- Default departure dates: dropdown shows only "Choose a departure date…" with no hardcoded options
Verify patchPage() sets ALL of these from the API response. If an element still has
hardcoded content after patchPage runs, it needs an ID added and a setText() call.

### 6.2 Request private dates — date validation
In the "Request private dates" modal:
- "Preferred from" date cannot be later than "Preferred to" date
- Validate on submit: if from > to, show inline error "End date must be after start date"
- Both dates cannot be in the past
- On submit: send enquiry to tour operator's email (POST /api/v1/bookings/enquiries/)
  The operator receives an email notification at their registered email address.
  Use Django send_mail() to the tour.operator.email.

### 6.3 "Where to go?" search bar on homepage — fix input + search
Two issues:
1. Cannot click or type in the search bar — the input is not focusable/interactive. Fix the HTML/CSS so the input receives clicks and keyboard input normally.
2. Search may not be working — on Enter or search icon click, navigate to adventures.html?q=<typed value>. adventures.html already reads the q param and filters results. Verify the full flow works end to end: type "Georgia", press Enter, see filtered results on adventures page.

---

## GROUP 7 — OPERATOR VERIFICATION

### 7.1 Operator verification flow
New field on User model: is_verified (BooleanField, default False).
New model: VerificationDocument (FK to User, document ImageField, submitted_at, reviewed_at, status: pending/approved/rejected, admin_notes).

Operator flow:
- After registering, operator sees a banner in their dashboard: "Your account is not yet verified. Upload your ID to start listing tours."
- Button: "Upload verification document" → opens a simple modal with file upload
- Endpoint: POST /api/v1/auth/verify/ (multipart — accepts ID document image)
- After upload: VerificationDocument created with status=pending, operator sees "Verification pending — we'll review within 48 hours."

Admin flow:
- In Django admin: VerificationDocument list shows pending documents
- Admin opens document, views uploaded ID
- Admin clicks Approve → User.is_verified = True, status = approved, send email to operator
- Admin clicks Reject → status = rejected, send email with reason

### 7.2 Only verified operators can submit for review
If operator.is_verified is False and they try to click "Submit for review":
Block submission. Show message:
"Your account needs to be verified before you can publish tours.
Upload your ID document to get verified. [Upload now →]"
Save Draft still works without verification — operator can prepare the tour while waiting.

---

## GROUP 8 — CONTACT PAGE (contact.html)

### 8.1 Email setup — console backend for local testing
Configure Django email in settings as described in SETUP NOTES above.
Use console backend locally: emails print to terminal.
Contact form: POST to /api/v1/contact/ → Django send_mail() to pul_khanna@yahoo.co.in.
Required fields: name, email, message — inline validation only, no browser alerts.
Remove "International support" section.
Success: "Message sent. We'll get back to you within 24 hours."

---

## IMPLEMENTATION ORDER (do in this sequence)

1. Fix Unicode escape in nav IIFE (Groups 3.3 and 4.1) — unblocks everything else visually
2. Fix operator signed-in nav state on all pages (4.2, 1.2, 1.3)
3. Group 2 — operator signup tab flow (2.1, 2.2) — blocking new registrations
4. Group 3 — settings photo upload (3.1, 3.2)
5. Group 5 — new tour page fixes (5.1, 5.2, 5.3, 5.4, 5.5, 5.6)
6. Group 6 — tour detail fixes (6.1, 6.2, 6.3)
7. Group 4 — dashboard tour management (4.3–4.7)
8. Group 7 — verification (new feature, after bugs are fixed)
9. Group 8 — contact email
10. Group 1 — operator landing page cleanup

---

## TEST CREDENTIALS
operator@waybound.com / Waybound2026!  (pk=1, role=operator, is_staff=True)
test@waybound.com / Waybound2026!  (pk=2, role=tourist)
API: http://127.0.0.1:8000/api/v1/
Contact/report email: pul_khanna@yahoo.co.in
