# WAYBOUND — FIXES & NEW ITEMS (V4)
# Only items from this session. Do not mix with V2 or V3.
# Items marked [PERSISTS] were attempted before and still broken.
# Read WAYBOUND_HANDOFF.md first for architecture context.
# ============================================================

---

## GROUP 1 — SEARCH BAR ("Where to go?") — affects multiple pages

### 1a. Add search bar to missing pages
The "Where to go?" search bar in the top nav exists on homepage and adventures page
but is missing from: contact.html, how-it-works.html, terms-of-use.html,
terms-for-guides.html, privacy-policy.html.
Check the homepage/adventures nav HTML for the exact search bar structure.
Add the identical search bar to the nav on all missing pages for UI consistency.
Do this BEFORE 1b so the bar exists on all pages first.

### 1b. Search bar broken on all pages except homepage
After 1a is done: the search bar input is not clickable/typeable on non-homepage pages.
Fix so that on ALL pages:
- Input is focusable and accepts keyboard input
- Pressing Enter or clicking search icon navigates to adventures.html?q=<typed value>
- adventures.html already reads the q param and filters — verify that still works
- Test on: homepage, contact, how-it-works, tour detail, adventures itself

---

## GROUP 2 — TOUR DETAIL PAGE (tour_detail_page.html)

### 2a. Report this listing — modal popup, not inline div
Currently clicking "Report this listing" shows a text input div below the link that
bleeds outside the main container div.
Fix:
- On click, open a centered modal popup (same style as the private dates modal)
- Modal contains: brief explanation, text area for reason, Submit button, Cancel/X button
- Input div must not bleed outside its parent container under any circumstances
- On submit: POST to /api/v1/contact/ with type="report", tour slug, and reason text
- Email sent to pul_khanna@yahoo.co.in: subject "Listing report: [tour name]"
- Success: close modal, show brief toast "Thank you. We'll review this listing."

### 2b. Booking sidebar — vertically centred/sticky while scrolling
The right-side booking widget panel should stay visible while the user scrolls the
main content. Current behaviour is either: it scrolls away with the page, or the
sticky positioning makes it feel cut off at top/bottom.
Fix: the sidebar column should be position:sticky with top offset calculated so
the booking card appears roughly vertically centred in the viewport as the user
scrolls — not pinned to the very top of the page.
Recommended: top: calc(50vh - (card-height / 2)) with a max that keeps it below the nav.
If card is taller than viewport: top: 80px (just below nav), let it scroll naturally.

### 2c. Lodge photo and room types not shown
Property photos uploaded per accommodation block (stay block) are not displayed on
the tour detail page.
Fix: in the "Where will we stay?" / accommodation section, show:
- Property photos as a small horizontal scroll (if uploaded)
- Room types listed below the property name with their price supplements
Check the API response — TourDetailSerializer includes stays[] with room_types[].
If the data is in the API response but not rendered, add the rendering logic.
If property photos are in a separate endpoint, fetch and display them.

---

## GROUP 3 — OPERATOR LANDING PAGE (operator.html)

### 3.1 Remove "How it works" text/button and the sign in button next to it
These are duplicated — they appear in the nav AND elsewhere on the page.
Remove from the nav: "How it works" link AND the "Sign in / Go to dashboard" button
that sits next to it in that area.
The sign in and CTA exist elsewhere — this nav area should be clean.

---

## GROUP 4 — OPERATOR DASHBOARD (operator-dashboard.html)

### 4a. Verification upload popup — don't show if already uploaded
Currently the "Upload your ID document" popup/banner shows every time the dashboard
loads, even after the operator has already uploaded their document or been verified.
Fix logic:
- If operator.is_verified = True: never show the popup
- If VerificationDocument exists with status=pending or approved: show "Verification pending" message instead of upload prompt, do not show the upload form again
- Only show the upload prompt if no document has ever been submitted

### 4b. Identity verification checkmark in account setup section
In the left panel account setup checklist, "Identity verification" item should show:
- ✓ green checkmark (same style as profile photo verified mark) when is_verified=True
- ⚠ warning/pending indicator when document submitted but not yet approved
- ○ empty circle when not submitted
This is on the left side panel, same row as the other setup checklist items.

---

## GROUP 5 — MY TOURS TAB (operator-dashboard.html)

### 5a. Archive and Delete — graceful UI confirmation boxes
Both archive and delete actions must show a styled modal confirmation box (not browser confirm()).
The modal should be centred, have the tour name in the heading, clear explanation of
what will happen, and two buttons: confirm action (red/danger) and Cancel.

Archive modal text:
"Archive [Tour Name]?
This tour will be hidden from travellers and no new bookings will be accepted.
Existing confirmed bookings remain valid. You can view archived tours by selecting
'Archived' in the filter. This action can be reversed by contacting support."
Buttons: "Archive tour" (red) | "Cancel"

Delete modal text (draft/review only):
"Delete [Tour Name]?
This will permanently remove this tour. This cannot be undone."
Buttons: "Delete permanently" (red) | "Cancel"

If tour has active future bookings and operator tries to archive:
"Cannot archive yet — you have X confirmed bookings with future departure dates.
Please cancel those bookings first before archiving this tour."
Show the booking references listed below the message.

### 5b. Delete vs Archive rules
- status=draft or status=review → show "Delete" option. If confirmed and no bookings exist: hard delete from DB. (Draft/review tours cannot have paid bookings so this is always safe.)
- status=live or status=paused with no future confirmed bookings → show "Archive" option
- status=live or status=paused WITH future confirmed bookings → show "Archive" option but block with the modal in 5a

### 5a and 5b must work from BOTH the My tours card actions AND the Django admin.

---

## GROUP 6 — NEW TOUR PAGE (operator-tour-create.html)

### 6a. Submit from My tours — check all mandatory fields not just image
[PERSISTS] Currently Submit for Review from the My tours tab does not check mandatory
fields properly — it submits even if image or other required fields are missing.
Fix: when operator clicks "Submit for review" from the My tours card on the dashboard,
before calling the publish API:
- Fetch the tour data from GET /api/v1/tours/<slug>/
- Check all mandatory fields (see mandatory field list below)
- If any are missing: show a graceful modal listing what is missing
  "This tour cannot be submitted yet. Please fill in the following:
   • At least 3 photos (currently: 1)
   • Tour description
   • At least 1 departure date"
- Provide a button: "Edit tour →" which goes to operator-tour-create.html?slug=<slug>
- Do NOT redirect automatically — let operator choose to go edit
- Do NOT submit to the API if any mandatory field is missing
This check must run BOTH from My tours tab AND from within the new tour page itself.

### 6b. Lodge single photo showing double on upload
When uploading a single accommodation/property photo, it shows twice in the preview
until a third photo is added, at which point it corrects itself.
This is a rendering bug in the photo grid update logic after upload.
Fix: after each photo upload, re-render the photo grid from the _photos array only once,
ensure no duplicate entries are pushed to the array.

### 6c. Form not retaining values on return
When operator saves draft, clicks Preview, views tour detail, then navigates back to
the new tour form — the form loses: price, requirement & info checkbox values and their
text inputs, departure dates, each day itinerary title/description, and other fields.
Root cause: form fields are populated from localStorage on load, but not all fields are
saved to localStorage on save — specifically the itinerary day values, checkbox states,
and their associated text inputs are not being read back and re-populated.
Fix:
- collectFormData() must capture: all itinerary day titles and descriptions, all
  requirement checkbox states and their associated text inputs, all departure dates,
  price, group size — everything the operator has entered
- On load in edit mode: after fetching from API (or localStorage), re-populate all
  these fields including itinerary blocks (add the day blocks first, then fill values),
  requirement checkboxes (tick them and show their text inputs), and departure dates
- This should work when returning from Preview (same session) and when coming back
  in a new session via ?slug= URL param

### 6d. [PERSISTS] Save draft + Submit for Review — below left panel, remove duplicated bottom buttons
The save/submit buttons exist in TWO places: below the left nav panel AND at the
bottom of the main content area.
Remove the duplicated set at the bottom of the main content div entirely.
Keep ONLY the set below the left panel.
If unsure which is which: the LEFT PANEL ones are inside the sidebar nav column.
The BOTTOM ONES are inside the main form content div near the Photos section footer.
Delete the bottom ones. Do not touch the left panel ones.

### 6e. Minimum data to save draft — prevent broken DB records
Save Draft should always work but needs enough data to create a valid DB record.
If Tour name is empty: auto-generate title as "Untitled tour [date]" rather than blocking.
This prevents the API returning a 400 error on save when title is blank.
All other fields optional for save.

### 6f. Save mandatory: minimum 8 field values to prevent table/record issues
When a draft is saved to the DB, ensure at minimum these 8 fields have values
(use defaults if operator hasn't filled them):
1. title — "Untitled tour [timestamp]" if blank
2. category — "Other" if none selected
3. difficulty — "Moderate" if not set
4. country — "" (blank allowed, but field must exist)
5. price_adult — 0 (placeholder, must be set before submit)
6. max_group — 12 (default)
7. currency — "RUB" (default)
8. tour_type — "multi" (default)
This ensures the DB record is valid and the My tours card renders without breaking.

---

## GROUP 7 — MANDATORY FIELDS SPECIFICATION

### For Save Draft — no mandatory fields from operator
Internally use defaults (see 6f above) to satisfy DB constraints.
Never block the operator from saving.

### For Submit for Review — these fields MUST be filled
Validate these before calling the publish API. Highlight and scroll to missing ones
on the new tour page. Show modal with list on the My tours tab.

MANDATORY FOR SUBMIT:
1. Tour name (not "Untitled tour...")
2. Category — at least 1 selected
3. Difficulty — must be chosen (not blank)
4. Country — must not be empty
5. Destination / city — must not be empty
6. Price per person — must be > 0
7. Max group size — must be > 0
8. At least 1 departure date
9. Full tour description — must not be empty
10. At least 1 day in itinerary with a title
11. At least 3 photos (first must be hero/order=0)

NOT MANDATORY FOR SUBMIT (optional, can go live without):
- Region / area
- Spots available (defaults to max_group)
- Meet-up time
- Departure city / End city
- Min/max age
- Tour language
- Headline impressions
- Difficulty note
- Tour video
- Requirement checkboxes
- Accommodation / stay blocks
- FAQs
- Cancellation policy
Any field not in the mandatory list above should have its * removed from the label
if it currently has one — misleading to mark optional fields as required.

---

## IMPLEMENTATION ORDER

1. Group 1 (1a then 1b) — search bar, widely visible, quick win
2. Group 6d — remove duplicated bottom buttons (simple, no logic)
3. Group 4a — fix verification popup showing repeatedly
4. Group 2a — report listing modal (CSS + backend endpoint)
5. Group 2b — sidebar sticky positioning
6. Group 5a/5b — archive/delete graceful UI
7. Group 6a — mandatory field check on submit from My tours
8. Group 6c — form retention (most complex, do carefully)
9. Group 6b — lodge photo double-render bug
10. Group 6e/6f — save draft defaults
11. Group 7 — audit all * labels, remove incorrect ones
12. Group 3.1, 4b, 2c — remaining UI polish

---

## TEST CREDENTIALS
operator@waybound.com / Waybound2026!  (pk=1, role=operator, is_staff=True)
test@waybound.com / Waybound2026!  (pk=2, role=tourist)
API: http://127.0.0.1:8000/api/v1/
Report/contact email: pul_khanna@yahoo.co.in

---

## GROUP 8 — MY TOURS CARD — IDENTIFICATION & DRAFT PROGRESS

### 8.1 Tour name — only mandatory field for Save Draft
Save Draft requires only one field: Tour name.
If name is empty when Save Draft is clicked: show inline message below the name field:
"Give your tour a name to save it."
Do not auto-generate "Untitled tour" — make the operator name it consciously.
All other fields remain optional for save. Never block save for any other reason.

### 8.2 My tours card subtitle — destination + price + days + last edited
Replace the current card meta line with a dynamic subtitle that shows available info
and graceful placeholders for missing info.

Card layout:
  [Hero photo or grey placeholder]
  Tour name                          [Status badge]
  Georgia · ₽89,000/person · 8 days
  Last edited 2 hours ago
  [Edit]  [Preview]  [Submit for review / Unpause / Copy link]

Subtitle logic (build from left to right, skip missing parts):
- Country/destination: show "Georgia" if set, show "Destination not set" in grey if missing
- Price: show "₽89,000/person" if set, show "Price not set" in grey if missing
- Days: show "8 days" if itinerary has days filled, omit entirely if 0 days
- Separator between items: " · "

Last edited line:
- Show relative time: "Last edited 2 hours ago", "Last edited just now", "Last edited 3 days ago"
- Use the tour's updated_at timestamp from the API

Examples of what the subtitle line looks like at different stages:
  Early draft:   "Destination not set · Price not set · Last edited just now"
  Partial:       "Georgia · Price not set · Last edited 5 minutes ago"
  Nearly done:   "Georgia · ₽89,000/person · Last edited yesterday"
  Complete:      "Georgia · ₽89,000/person · 8 days · Last edited 3 Jan 2026"

This makes the card a visual progress indicator — operator sees at a glance what still needs filling without a separate progress bar.

### 8.3 No sequential reference codes needed for now
Do not add TRP-OP-XXXX style reference codes to tour cards.
Destination + last edited is sufficient for identification at current scale.
Booking references (TRP-XXXXXX) already exist for support conversations.
Can revisit if operators reach 10+ tours and need further identification help.
