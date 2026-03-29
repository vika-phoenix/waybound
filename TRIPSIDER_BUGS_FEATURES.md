# WAYBOUND — BUGS & FEATURES LIST FOR CLAUDE CODE
# Share this file at the start of every Claude Code session.
# All items are confirmed and ready to implement unless marked [DECISION NEEDED].

---

## 1. Delete Tour — Graceful handling
When an operator deletes/archives a tour:
- Show a confirmation dialog explaining what happens to existing bookings
- If confirmed bookings with future departure dates exist, block deletion and list them explicitly
- Only allow archiving if no active bookings exist, or after all active bookings have been manually cancelled
- Hard delete should never exist — always archive (status → archived), data preserved forever for booking history, reviews, and financial records

---

## 2. Save Draft / Submit for Review — Navigation & UI

**Single location for actions:**
Remove the top nav save/submit buttons entirely. Keep only the bottom sticky left panel as the single place for both Save Draft and Submit for Review.

**After Save Draft:**
Instead of a fading indicator, show a small persistent "← My tours" button that stays visible after saving. This is cleaner than a previous tours list in the panel. The button takes them directly to the My tours tab on the dashboard. No fading — stays until they navigate away or save again.

**After Submit for Review:**
Redirect directly to operator-dashboard.html with ?tab=tours so the My tours tab auto-opens.

**Dashboard tab switching:**
The dashboard must read ?tab=tours from the URL on load and auto-activate that tab. Currently hash-based switching doesn't work reliably.

---

## 3. Departure City field — Remove, map to End City
Both "Destination city" and "End city" always held the same value. Remove "Destination city" from the form entirely. Keep only "End city" (rename to "Meeting & end point" for clarity). In the tour detail page and all API serializers, anywhere that previously read from destination_city must be remapped to use the end city / meeting point field. Be careful to update: tour_detail_page.html display, TourListSerializer, TourDetailSerializer, and any fixture data.

---

## 4. Emoji — Remove completely. Hero image mandatory for submit.
Remove the emoji field from the tour create form, tour cards, and all display logic. Do not auto-assign emoji either — remove the concept entirely.

**Hero image mandatory for submit (not for save):**
- Save Draft: no mandatory fields — operator can save partial progress including images, checkboxes, departure dates, all input at any stage
- Submit for Review (from new tour page): validate all mandatory fields. If hero image is missing, highlight the photo upload section and auto-scroll to it with a clear message "At least one hero image is required before submitting"
- Submit for Review (from My tours tab on dashboard): show a graceful modal/message listing which mandatory fields are missing, with a link to Edit the tour. Do not redirect silently.

**Mandatory fields for submit:**
Tour name, category, country, meeting/end point, price per person, max group size, at least 1 hero photo.

---

## 5. Add Day Button — Single instance only
Remove the "Add day" button from the top of the itinerary section. Keep only the button at the bottom of the day list. One is enough.

---

## 6. Tour Detail Page — Show up to 5 images in mosaic
Expand the photo mosaic to show up to 5 images:
- Hero image: large, occupies left half
- Right half: 2×2 grid of 4 smaller images
- If fewer than 5 photos exist, hide the empty slots (no blank placeholders)
- If more than 5 photos exist, show a "+ X more" badge on the last visible slot that opens the full gallery modal
This is the standard pattern used on Viator, GetYourGuide, Airbnb.

---

## 7. Preview button — New tour page and My tours tab

**New tour page:**
After Save Draft is pressed and a slug exists (tour has been created in DB), show a Preview button in the left panel below the Save Draft button. Opens tour_detail_page.html?slug=<slug>&from=operator in the same tab (not a new window).

**My tours tab (dashboard):**
The existing Preview button on each tour card should also add ?from=operator to the URL.

**Back navigation on tour detail page when from=operator:**
When ?from=operator is present in the URL, show a sticky bar at the top of the tour detail page:
"← Back to My tours  |  Edit this tour"
"Back to My tours" goes to operator-dashboard.html?tab=tours.
"Edit this tour" goes to operator-tour-create.html?slug=<slug>.
This is the same pattern already implemented for the tourist "← Change date" link.

---

## 8. Property Type — Not saving correctly
When adding accommodation blocks in the tour form, only "Hotel" saves correctly. All other property types (Hostel, Guesthouse, Camping/glamping, Homestay, Mountain hut) are broken.
Fix in: collectFormData() accommodation block selector, buildApiPayload() mapping, and verify StayBlock serializer accepts all values. The select element value must be read correctly and sent as property_type in the API payload.

---

## 9. Category — Allow multiple selection
Change tour category from a single dropdown to a multi-select. Recommended UI: tag-style checkbox group where operator taps each category to toggle it (e.g. Trekking, Cultural, Wildlife — all selected simultaneously).
Backend: change Tour.category from CharField to JSONField (list of strings). Update TourWriteSerializer, TourListSerializer, and the public filter endpoint to support ?category=Trekking,Wildlife (comma-separated).

---

## 10. Requirements & Info — Checkbox with conditional input
In the Requirements / What to bring section, when an operator ticks a checkbox item (e.g. "Passport required", "Travel insurance required"), show a free-text input box inline next to it for additional detail. Input is optional but only visible when the checkbox is ticked. Currently checkboxes have no associated input.

---

## 11. Operator Landing Page (operator.html) — Top form + bottom section

**Top quick-signup form:**
Remove the name/email/country/tour-type quick entry form from the hero section entirely. Replace with a single prominent CTA button: "Apply as a guide →" that goes directly to signup-operator.html. No prefilling needed — the form was adding friction, not reducing it.

**Bottom section (just above footer):**
- "Create your guide profile" → links to signup-operator.html (currently goes to tourist signup — wrong)
- "Talk to our team first" → links to contact.html
- "Start listing for free" → style as plain text link or subtle ghost button only. No background colour, no colour change on hover. Should not compete visually with the main CTA.

---

## 12. Operator Signup (signup-operator.html) — Email field + step validation
- The email field must not be visually highlighted or outlined differently from other fields on the page
- All fields marked with * must be genuinely validated before the Next button allows progression to the next step. Currently starred fields are not blocking — fix step validation to check all required fields before advancing
- Email format errors: show inline red message below the field, not a browser alert popup
- This applies to all three steps — each step's required fields must be validated on Next click

---

## 13. Tour Detail Page — Total price display + disclaimer
Show the calculated total price in the booking widget (adults × price_adult + children × price_child). This should calculate and display regardless of accommodation data — do not make it dependent on property type.

Below the total price, show a small grey note:
"Approximate price for standard accommodation. Final price including room type and any supplements will be confirmed on the booking details page."

---

## 14. Booking Flow — "Check availability" replaced + date handling

**Remove "Check availability" button entirely.**
Replace with a "Book now" button that:
- Is greyed out and unclickable when no departure date is selected
- Becomes active (full colour) as soon as a date is selected
- Clicking it proceeds directly to the booking form page

**Departure date dropdown — sold out dates:**
Dates where spots_left = 0 should not appear in the dropdown at all (cleaner than crossing them out). Dates with 1-3 spots remaining should show "Only 2 spots left" next to the date label.

**Slot count handling:**
- Spots left count updates in real time as adults + children pax count changes in the widget (if 2 adults selected and only 1 spot left, show warning before allowing booking)
- When tourist reaches the booking confirmation page, re-validate spot availability server-side. If slots have been taken by another user in the meantime, show a clear message: "Sorry, this departure is now full. Please select another date." and redirect back to the tour detail page with the date selector open. This is how Viator and GetYourGuide handle it.

---

## 15. Contact Page — Email recipient + form fixes
- Set contact form submission recipient to: pul_khanna@yahoo.co.in
- On submit, send email to that address. Use Django's send_mail() on a new POST /api/v1/contact/ endpoint, or EmailJS on the frontend if backend email is not set up yet
- All mandatory fields (name, email, message) validated gracefully with inline messages, not browser alerts
- Remove the "International support" section from the page entirely

---

## 16. Private Tours — How it works (confirmed approach)

**Background:** Private tours are not a common public-listing feature on mainstream platforms like Viator. The standard industry approach is: tourist sends an enquiry, operator reviews and confirms, then shares a private link. This is better than a toggle because it prevents operators from accidentally hiding tours, and it creates a proper conversation before commitment.

**Confirmed flow for Waybound:**
1. Tourist clicks "Request private dates" on any live tour detail page
2. Fills the enquiry modal (dates, group size, message) — this already exists
3. Operator receives the enquiry in their dashboard Enquiries tab
4. Operator reviews, agrees on dates and price, then creates a new tour with "Private" toggle ON
5. The private tour (status: live, is_private: true) does NOT appear on homepage, adventures page, or any public listing
6. The operator copies the direct link from their My tours card and shares it with the tourist privately (WhatsApp, email, etc.)
7. Tourist opens the link — sees the full tour detail page and can book normally

**Backend changes needed:**
- Add is_private boolean field to Tour model (default False)
- Public list endpoint: filter(status=live, is_private=False) — private tours excluded even when live
- Public detail endpoint: allow access to private tours via direct slug link (do not 404 them)
- Operator tour list: show all including private ones

**Frontend changes needed:**
- Tour create form: add "Private listing" toggle (already exists, needs backend wiring)
- My tours card: if is_private=True, show a "Copy link" button with the direct URL
- Adventures/homepage: already filtered by API, no change needed once backend filters correctly

---

## 17. Departure Dates — Cannot be in the past
- Date picker for departure dates in the tour create form: set min attribute to today's date dynamically in JS (not hardcoded)
- Validate server-side in DepartureDate serializer: start_date must be >= today
- If operator tries to submit a past date, show inline error: "Departure date cannot be in the past"

---

## 18. "Send a message" — Route to operator email
The "Send a message" button/link on the tour detail page should open a mailto: link to the tour operator's email address, not redirect to the site Contact page. The message is for the tour operator, not Waybound support.
If the operator's email should not be publicly exposed, route it through the enquiry system instead: clicking "Send a message" opens the existing private tour enquiry modal pre-filled with subject "General enquiry about [tour name]".

---

## 19. Operator Dashboard Nav — Avatar initials broken
The "OA" text showing in the nav dropdown instead of the operator's initials is a Unicode escape bug in the dropdown HTML string. The nav JS builds dropdown HTML using string concatenation with escaped Unicode — the dashboard icon emoji codes are malformed. Fix: check the navDropdown innerHTML builder in operator-dashboard.html, specifically the line that sets the operator dashboard menu item icon. Replace escaped Unicode with actual characters or correct escape sequences.

---

## 20. Account Settings — Avatar upload not working
Profile photo upload in settings.html is not wired to the backend. Fix:
- settings.html: on file input change, read the file, send PATCH /api/v1/auth/me/ as multipart/form-data with the image
- Backend: /api/v1/auth/me/ PATCH endpoint must accept multipart (use MultiPartParser), save to User.avatar ImageField, return updated user object
- This is part of T17 remnant — backend endpoint exists, needs parser_classes = [MultiPartParser, FormParser] added and avatar field included in UserMeSerializer

---

## ADDITIONAL CONTEXT FOR CLAUDE CODE

**Test users:**
- operator@waybound.com / Waybound2026! (pk=1, role=operator, is_staff=True)
- test@waybound.com / Waybound2026! (pk=2, role=tourist)

**API base:** http://127.0.0.1:8000/api/v1/

**Key rule:** Read the actual file before changing it. Run the server and test in browser. Do not guess at HTML structure — inspect it.

**Task order recommendation:**
Start with items that are pure frontend (2, 5, 7, 11, 12, 17, 19) as they have no backend dependency and can be verified immediately in browser. Then move to items needing both frontend and backend (3, 9, 14, 16, 20). T13, T14 payment system is separate and needs YooKassa/Stripe sandbox credentials before starting.

---

## 16. Private Tours — REVISED (replaces previous entry)

Two separate features that work together:

**Feature A — Tourist "Request private dates" (already exists, keep as-is):**
Tourist clicks "Request private dates" on any live public tour detail page. Fills the enquiry modal (preferred dates, group size, message). Operator receives this in their dashboard Enquiries tab. No change to this flow.

**Feature B — Operator "Private listing" toggle (create a hidden bookable tour):**
This is for after the operator and tourist have agreed on dates and price (either via the enquiry above, or via WhatsApp/email outside the platform). The operator creates a new tour, toggles "Private listing" ON, sets the agreed departure date and price, and saves.

Behaviour of a private tour:
- Does NOT appear on homepage, adventures page, or any public search
- IS accessible via its direct URL (tour_detail_page.html?slug=<slug>) — no 404
- Operator sees it in their My tours tab with a "Copy link" button on the card
- Operator shares that direct link with the specific tourist
- Tourist opens the link, sees the full tour detail page, and books normally

Backend:
- Tour model already has is_private boolean field (add if not present, default False)
- Public list endpoint: filter(status=live, is_private=False)
- Public detail endpoint: allow access regardless of is_private — do not 404
- Operator list: show all tours including private

Frontend:
- Tour create form: "Private listing" toggle already exists — wire is_private field to API payload
- My tours card: if is_private=True, show lock icon + "Copy link" button with the full direct URL
- Adventures / homepage: no change needed once backend filter is correct

---

## 21. Property Photos — Optional per accommodation block
In the tour create form, each accommodation (stay block) should have an optional "Add property photos" button. Operator can upload 1-4 photos of the property (hotel room, glamping tent, guesthouse exterior etc.).

Backend:
- Add a PropertyPhoto model: FK to StayBlock, image field, order int
- Or simpler: add a photos JSONField to StayBlock storing URLs after upload
- New endpoint: POST /api/v1/tours/<slug>/stays/<id>/photos/

Frontend (tour create form):
- Each stay block gets a small photo upload row below the existing fields
- Shows thumbnail previews after upload, with remove button
- Same multipart upload pattern as tour photos

Tour detail page:
- In the "Where will we stay?" / accommodation section, show the property photos as a small horizontal scroll or 2-column grid
- Only shown if property photos exist — entirely optional, no placeholder if empty

---

## 22. Use Previous Tour as Template
In the tour create form, add a "Start from a template" option at the very top of the form (before any fields). When clicked, shows a dropdown/modal listing the operator's previously created tours. Selecting one pre-fills all form fields with that tour's data (title gets "(Copy)" appended, all other fields copied as-is including itinerary days, stay blocks, cancel policy, FAQs). Photos are NOT copied — operator must upload fresh photos for the new tour. After pre-filling, the operator edits whatever needs changing and saves/submits as a new tour with a new slug.

Implementation:
- On page load in new tour mode (no ?slug= param), fetch GET /api/v1/tours/operator/ to get operator's tour list
- Show "Use a previous tour as template" link/button at top of form
- On selection, fetch GET /api/v1/tours/<slug>/ and populate all form fields
- Clear _photos array — do not copy photos
- Clear departure dates — operator sets new ones
- Title: append " (Copy)" to original title

---

## 23. Operator Signup (signup-operator.html) — Full UI/UX Rewrite

Current problems:
- Mandatory fields not validated — Next button advances regardless
- Second tab content appends below first tab instead of replacing it
- No Back button
- Third tab has no Submit button in the right place

**Correct flow:**
- Three tabs shown in the step indicator bar at top (Step 1, Step 2, Step 3)
- Only the current step's content is visible — previous step content is hidden (display:none), not stacked below
- Each tab has a Next button (Steps 1 and 2) or Submit button (Step 3)
- Steps 1 and 2 also have a Back button that returns to previous step
- Clicking a step in the top indicator bar only navigates to that step if all previous steps have been completed (mandatory fields filled). Cannot skip ahead.
- On Next click: validate all starred (*) required fields in the current step. If any are empty or invalid, highlight them red with inline error message and do NOT advance. Only advance when all required fields pass.

**Step content:**
- Step 1: Personal details (name, email, phone, country, password)
- Step 2: Tour operations (business name, experience, group size, languages, bio)
- Step 3: Review summary + terms agreement + Submit

**Validation rules per step:**
- Step 1 required: first name, last name, email (valid format), password (min 8 chars)
- Step 2 required: at least one tour type or category selected, bio (min 50 chars)
- Step 3 required: all consent checkboxes ticked before Submit enables

**Alternative UI suggestion (if simpler):**
A single-page vertical form with clear section dividers and a floating "Submit application" button that only activates once all required fields across all sections are filled. Simpler to implement, less error-prone than multi-step. Good for desktop. Your call on which approach to use.
