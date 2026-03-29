# WAYBOUND — FIXES & NEW ITEMS (V5)
# Only new items from this session. Do not mix with V2/V3/V4.
# Read WAYBOUND_HANDOFF.md first for architecture context.
# ============================================================

---

## CRITICAL BUG — FIX FIRST

### C1. Tour info disappears when logged in after going live or sending message
PRIORITY: Fix before anything else. This is the most severe bug.

Symptom: After a tour goes live OR after sending a message, the tour detail page
shows blank/missing info when the user is logged in. When logged out, the info
shows correctly.

Root cause hypothesis: The tour detail page loadTour() likely checks for a JWT token
and when one is present, tries to call a different (authenticated) endpoint that either
requires different permissions, returns a different response shape, or fails silently.
When logged out, it calls the public endpoint which works fine.

Fix:
- Tour detail page must ALWAYS use the public endpoint GET /api/v1/tours/<slug>/
  regardless of login state. Do not switch endpoints based on auth status.
- If there is any code that does: "if logged in, fetch from /operator/ endpoint,
  else fetch from public endpoint" — remove it. Always use public endpoint for display.
- The public endpoint already returns full tour data for live tours.
- After fixing, test: log in as operator, go live, view tour detail — all info must show.
- Also test: log in as tourist, send message, return to tour detail — info must show.

---

## GROUP 1 — TOUR DETAIL PAGE (tour_detail_page.html)

### 1.1 Request private dates — prefill traveller counts from booking widget
When tourist opens the "Request private dates" modal, prefill the Adults, Children,
and Infants fields with whatever values the tourist has already set in the travellers
section of the booking widget on the same page.
Read from the bkPax object (already exists in JS): bkPax.adult, bkPax.child, bkPax.infant.
Set these as the default values in the modal steppers on open, not hardcoded defaults.

### 1.2 Request private dates — date picker clicks anywhere on box
The date "from" and "to" inputs in the private dates modal should open the date picker
when clicking anywhere on the styled date box, not just the arrow icon.
Same fix as the main departure date picker — use pointer-events:none on the hidden input,
trigger showPicker() from the wrapper div onclick.
Also: "from" date cannot be later than "to" date. Validate on modal submit.

### 1.3 Price updates dynamically as traveller count changes
When tourist changes Adults, Children, or Infants count in the booking widget,
the total price shown in the sidebar must update immediately.
Formula: total = (adults × price_adult) + (children × price_child)
Infants are free — do not add to total.
Child price: use tour.price_child if set, otherwise 85% of price_adult.
Remove decimal points from child price display — show ₽75,650 not ₽75,650.00.
Wire the stepper buttons (+ / −) to call a recalculate function after each change.

### 1.4 Category shown as tags below tour title
Categories selected by operator must display as tag chips on the tour detail page,
in the same area as the existing tag row.
Read from t.category (now a list since multi-select). Render each as a styled tag.
These replace the current hardcoded tags (Road trip, Photography etc.) — those were
Kenya demo data and should already be gone.

### 1.5 Meet-up time — show in departure details
If the operator set a meet-up time, show it alongside the departure date in the
booking widget: "15 Mar 2026 · 09:00 AM". If no meet-up time set, show date only.

### 1.6 Story & Highlights / Difficulty note — keep, show under About section
Show the difficulty note as a collapsible sub-section inside the About section,
below the main description. Label: "What to expect physically."
If difficulty note is empty, hide the sub-section entirely.

### 1.7 Room types, property type, comfort level — show in accommodation section
These fields are filled by the operator but currently not displayed on tour detail.
In the "Where will we stay?" section, for each stay block show:
- Property name (already shown)
- Property type (Hotel / Guesthouse / Camping etc.) — show as a small tag
- Comfort level (Budget / Standard / Superior / Luxury) — show as text
- Room types offered — list each with its price supplement:
  "Single room (+₽4,500)" / "Twin room (included)" / "Dorm (−₽2,000)"
If no accommodation data: hide the section entirely. Do not show empty placeholders.

### 1.8 Region / area — show on tour detail
If operator filled region/area field, show it in the location/destination area of the
page, e.g. "Georgia · Greater Caucasus" (country · region).

### 1.9 Destination city at top — clarify display
"Destination / city" is the searchable location field (e.g. "Tbilisi", "Kazbegi").
On tour detail, show it as the location line below the title, not as a large header.
Format: "📍 Kazbegi & Svaneti, Georgia" — city + country.
This already exists as tourDest — just ensure it reads from the API correctly.

### 1.10 See the route / View on map — link to Google Maps
"See the route" and "View on map" should link to Google Maps pre-filled with the
departure city as the search term.
URL: https://www.google.com/maps/search/?q=<departure_city>
Open in new tab. If departure city not set, hide these links entirely.

### 1.11 Where will we stay? / Comfort — hide if no data
If the tour has no stay blocks filled in, hide the entire accommodation/comfort
section from the tour detail page. Do not show empty boxes or placeholder text.
When stay data exists, show it as per 1.7 above.

### 1.12 Tour detail always shows max 5 photos — fix to show all uploaded
Current behaviour: mosaic shows max 5 photos regardless of how many were uploaded.
Fix: show hero + up to 4 in the collage (5 visible total). If more than 5 uploaded,
show a "+ X more" badge on the last slot. Clicking it opens the full gallery modal
which shows ALL uploaded photos, not just 5.

### 1.13 Tour submitted — show graceful confirmation UI
After operator submits tour for review, instead of a plain alert() popup, show a
styled full-screen or centred modal:
  ✓  Tour submitted for review
  "Your tour has been submitted. Our team will review it within 48 hours.
   You'll receive an email at [operator email] once it's approved."
  [Go to My tours] button
Nice animation (checkmark drawing in, slight bounce). Dismiss on button click.

---

## GROUP 2 — NEW TOUR PAGE (operator-tour-create.html)

### 2.1 "How demanding?" difficulty field — remove auto-select / placeholder fix
Currently the difficulty select auto-fills "Moderate" or similar as a default, meaning
operators may not realise they haven't actively chosen it.
Fix: set the default option to an unselectable placeholder:
  <option value="" disabled selected>Select difficulty level</option>
Make it required for submit. If blank on submit, highlight and show error.

### 2.2 Requirements & info — UI fix, multiple open at once
Keep accordion style but allow multiple items open simultaneously.
Clicking one item should NOT close other open items.
Currently the accordion auto-collapses others — remove that behaviour.
Each item has its own independent open/closed state.

### 2.3 Requirements & info — Additional notes placement
"Additional notes" text area should appear below ALL the requirement checkboxes
as a general free-text field, not as part of any specific checkbox item.
Label: "Additional notes for travellers (optional)"
Show it always visible, not inside a collapsible.

### 2.4 Tour language — multiple checkbox selection
Change "Tour language" from a single input/select to a checkbox group:
  □ English  □ Russian  □ Georgian  □ Spanish  □ French  □ German  □ Arabic  □ Other
Allow multiple languages selected simultaneously.
Store as JSON array in the API (e.g. ["English", "Russian"]).
On tour detail page: show selected languages as comma-separated text or small tags.

### 2.5 Child price — remove decimal display
Show child price as ₽75,650 not ₽75,650.00 everywhere:
- New tour form price preview
- Tour detail booking widget
- Booking confirmation page
- My tours card if shown
Use parseInt() before formatting with toLocaleString().

### 2.6 Photos — duplicate upload bug (critical)
Uploading photos creates duplicates in the _photos array and grid display.
Example: upload 3 photos → shows 5. Upload 5 more → shows 12.
Root cause: photos are being pushed to _photos array multiple times — likely the
handlePhotoUpload function is called multiple times per upload event, or the array
is not cleared before re-render, or both the old and new photos are being appended.
Fix:
- Ensure handlePhotoUpload only fires once per file input change event
- Before pushing new photos, check for duplicates by filename or dataUrl
- renderPhotoGrid() must render from _photos array state only — never append to existing DOM
- After fix: upload 3 → shows 3. Upload 3 more → shows 6. No duplicates.

### 2.7 Adult price always forgotten — retain in form
"Price per adult" field value is lost on page reload/return even in edit mode.
Ensure price_adult is included in both:
- collectFormData() — captured and saved to localStorage and API
- Edit mode init — read from API response and set document.getElementById('fPrice').value
Verify the field ID matches exactly what collectFormData() reads from.

### 2.8 Accommodation 5MB note
In the accommodation section notes/description field, add a small helper text below:
"Max 5MB per photo. Accepted formats: JPG, PNG, WEBP."
This applies to property photos for each stay block.

### 2.9 Day itinerary — starting location
Keep "Starting location" as an independent field per day (each day can differ).
Day 1 starting location does NOT auto-sync with Departure city — they are separate.
The departure city is the overall meeting point; day 1 starting location might be
a hotel lobby or specific landmark.
Add a small hint below the field: "e.g. Hotel lobby, Tbilisi city centre"

### 2.10 Cancellation policy — show site standard, skip auto-check for now
In the cancellation policy section of the form, add a collapsible info box at the top:
"Waybound standard cancellation policy: Full refund if cancelled 30+ days before
departure. 50% refund 14-30 days before. No refund within 14 days."
Show this as read-only reference so operators know the baseline.
Skip the admin auto-alert for now — that is a future feature.

### 2.11 Payment page — not pulling correct tour data
The booking/payment page is showing Georgia tour hardcoded data instead of the
selected tour's actual data.
Fix: booking.html must read tour slug from URL params (?slug=) and fetch tour data
from GET /api/v1/tours/<slug>/ to populate price, days, tour name, and other details.
Do not use any hardcoded template data. If slug param missing, show error.

---

## GROUP 3 — MY TOURS TAB (operator-dashboard.html)

### 3.1 Preview opens in same window — not new tab
My tours card Preview button must use window.location.href not window.open().
Opens tour_detail_page.html?slug=<slug>&from=operator in the same tab.
[PERSISTS from previous lists — fix carefully]

### 3.2 Archive shown under Archived filter only — already decided
Confirmed: operator can see archived tours by selecting "Archived" in the filter.
"All statuses" filter does NOT include archived tours.
This was already specified in V4 item 4.3 — verify it is implemented correctly.

### 3.3 Show child price on tour card — yes
Add child price to the tour card meta line if set:
"₽89,000/person · Child ₽75,650" — no decimals on either.
If child price not set, show adult price only.

---

## FIELDS TO SHOW ON TOUR DETAIL — COMPLETE MAPPING
This is the definitive list of what goes where on tour_detail_page.html.
Use this to audit what is currently missing.

HERO AREA:
- Tour title
- Rating + review count
- Days · Max group size · Tour languages (comma separated)
- Destination city, Country (📍 Kazbegi, Georgia)
- Category tags (chips/tags from operator's selected categories)

PHOTO MOSAIC: hero + up to 4 collage, + X more badge

OVERVIEW STRIP (3 columns):
- Difficulty: label + stars/dots + exertion description
- Comfort: label + stars + comfort level text (hide if no accommodation)
- Route: departure city → end city, link to Google Maps (hide if no departure city)

TAGS ROW: category tags (same as hero area)

ABOUT SECTION:
- Full tour description
- "What to expect physically" (difficulty note) — collapsible, hide if empty

MEET-UP / DEPARTURE:
- Next departure date + meet-up time
- Spots left count
- Departure date dropdown (real dates from API, sold-out hidden)

DAY BY DAY ITINERARY:
- Day number, title, starting location, description, meals

WHERE WILL WE STAY (hide entire section if no stays):
- Property name, type tag, comfort level
- Room types with price supplements
- Property photos horizontal scroll (if uploaded)

REQUIREMENTS & INFO:
- Only show checked items from operator's requirement checkboxes
- Each shows its associated text note if filled
- Additional notes below all items

CANCELLATION POLICY:
- Show tiers if operator filled them
- If none filled: show Waybound standard policy as fallback

REVIEWS SECTION:
- Show 3 by default, See all / Collapse

---

## IMPLEMENTATION ORDER FOR THIS SESSION

1. C1 — Critical bug: tour info disappears when logged in (fix first)
2. 2.6 — Photo duplicate bug (critical, blocks testing everything else)
3. 1.3 — Dynamic price update on pax change
4. 2.11 — Payment page wrong tour data
5. 1.1, 1.2 — Request private dates prefill + date picker fix
6. 2.1 — Difficulty field placeholder fix
7. 3.1 — Preview same window
8. 1.7, 1.11 — Accommodation section show/hide
9. 1.4, 1.5, 1.8 — Category tags, meet-up time, region on tour detail
10. 2.4 — Tour language multi-checkbox
11. 2.2, 2.3 — Requirements UI fixes
12. 1.10 — See route / map links
13. 1.6 — Difficulty note placement
14. 1.13 — Tour submitted graceful UI
15. 2.5, 2.7, 2.8, 2.9, 2.10 — Remaining new tour form polish
16. 1.12 — Full gallery modal with all photos
17. 3.2, 3.3 — My tours archive filter + child price on card

---

## TEST CREDENTIALS
operator@waybound.com / Waybound2026!  (pk=1, role=operator, is_staff=True)
test@waybound.com / Waybound2026!  (pk=2, role=tourist)
API: http://127.0.0.1:8000/api/v1/

---

## ADDENDUM — Answers to deferred questions

### A1. Archive visibility — operator can see under Archived filter
Confirmed: operator can see their archived tours by selecting "Archived" in the
My tours filter. Not shown in "All statuses." Already specified in V4 4.3.

### A2. Story & Highlights / Difficulty note — keep, show below difficulty label
An additional difficulty note is meaningful — "Moderate" means different things on
different tours. Keep the field in the new tour form.
On tour detail: show the note as a short italic line directly below the difficulty
label in the overview strip. Example:
  Difficulty: Challenging
  "Involves 6-8 hours of hiking per day on mountain terrain above 2000m."
If difficulty note is empty, show nothing. Do not show a placeholder.

### A3. Departure city vs Day 1 starting location — keep independent
These are genuinely different things:
- Departure city = the city tourists fly/travel to (e.g. "Tbilisi")
- Day 1 starting location = exact meeting point (e.g. "Rooms Hotel lobby, Rustaveli Ave")
Keep them as separate independent fields. Day 1 starting location does NOT sync with
departure city. Instead, show the departure city as placeholder hint text in the
Day 1 starting location field: placeholder="e.g. Hotel lobby, Tbilisi city centre"
This is standard practice on Viator and G Adventures.
On tour detail: show Day 1 starting location in the itinerary section as-is.

### A4. Optional extras — show on tour detail AND booking page
Extras filled by operator (name + price per person) must appear in two places:
Tour detail page: collapsible "Add-ons available" section below the day itinerary.
  Each extra shows: name, description (if any), price per person.
  "Extras are optional and can be selected during booking."
Booking page: checklist of available extras with checkboxes.
  Selecting an extra updates the running total dynamically.
  On booking form submission, selected extras are included in the booking payload
  as a JSON array: extras: [{name: "...", price: 5000}]
Backend: Tour model needs an extras JSONField: [{name, description, price_per_person}]
New tour form: already has an extras section — wire it to the API payload.
This feeds into T19 payments naturally.

### A5. Cancellation policy — show on tour detail near booking widget
Cancellation tiers filled in the new tour form must display on tour detail.
Placement: collapsible section below the booking widget card, labelled
"Cancellation policy." Show each tier as a clear row:
  ✓ Free cancellation if cancelled 30+ days before departure
  ⚠ 50% refund if cancelled 14-30 days before departure
  ✗ No refund within 14 days of departure
If operator has not filled any cancellation tiers: show the Waybound standard policy
as a fallback (same text as Trust & Safety page cancellation section).

Auto-check against platform standard (when operator fills tiers in new tour form):
Compare each operator tier against the platform minimum:
  Platform minimum: full refund 30+ days, 50% refund 14-30 days, no refund <14 days
If operator's policy is MORE restrictive than the platform minimum at any tier
(e.g. no refund until 45 days, or 0% refund between 14-30 days), flag it:
  Show inline warning in the form: "This policy is stricter than Waybound's standard.
  Admin will review before the tour goes live."
  Set a flag on the tour: has_custom_cancellation = True
  Admin sees this flag in the tour review queue and receives an email:
  "Tour [name] has a non-standard cancellation policy. Please review before approving."
  Email to: pul_khanna@yahoo.co.in
Backend: add has_custom_cancellation BooleanField to Tour model, set in TourWriteSerializer
when policy tiers are saved, by comparing against hardcoded platform minimums.

---

## ADDENDUM 2 — Difficulty note + exertion mapping

### Difficulty display on tour detail — two layers

**Current state:**
- Input form: difficulty dropdown (Easy/Moderate/Challenging/Expert) at the top PLUS
  a free-text "Difficulty note" field (fDiffNote) in Story & Highlights section
- Tour detail: exertion-desc div currently shows hardcoded Kenya demo text — NOT mapped
  from the difficulty dropdown. No exertionDescMap exists in the JS.

**Fix — implement two-layer display on tour detail:**

Layer 1 — Pre-mapped system description (always shown, derived from difficulty dropdown):
  Easy        → "Relaxed pace. Minimal physical effort. Suitable for all ages and fitness levels."
  Moderate    → "Some fitness required. Expect moderate walking and light physical activity."
  Challenging → "Good fitness needed. Expect long active days and demanding terrain."
  Expert      → "High fitness required. Strenuous conditions. Prior experience essential."

Layer 2 — Operator's specific note (fDiffNote, shown below Layer 1 only if filled):
  Shown in italic, smaller text:
  e.g. "8 km of walking per day on uneven mountain terrain above 2000m."

Result on tour detail:
  Exertion level: Challenging
  "Good fitness needed. Expect long active days and demanding terrain."
  "8 km of walking per day on uneven mountain terrain above 2000m."  ← italic, only if filled

If fDiffNote is empty: show Layer 1 only.
If fDiffNote is filled: show both, Layer 2 in italic below Layer 1.

**Implementation:**
In patchPage(t) in tour_detail_page.html:
- Add exertionDescMap with the four descriptions above
- Set id="tourExertionDesc" element text from exertionDescMap[t.difficulty]
- Add a new element id="tourExertionNote" (italic, smaller) below exertion-desc
- Set tourExertionNote to t.difficulty_note if present, hide it if empty
- Ensure fDiffNote value is saved in collectFormData() as difficulty_note
- Ensure difficulty_note is included in buildApiPayload() and TourWriteSerializer

**Wire fDiffNote to API:**
In operator-tour-create.html collectFormData():
  difficulty_note: (document.getElementById('fDiffNote') || {}).value || ''
In buildApiPayload(): include difficulty_note in the payload object.
In Tour model: add difficulty_note = CharField(max_length=300, blank=True)
In TourDetailSerializer: include difficulty_note field.
