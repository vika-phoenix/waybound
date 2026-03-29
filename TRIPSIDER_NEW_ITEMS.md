# WAYBOUND — NEW ITEMS (session additions)
# These are NEW items not in the previous bugs list.
# Read alongside WAYBOUND_HANDOFF.md and WAYBOUND_BUGS_FEATURES_V2.md

---

## 1. Deposit/discount — remove from tour detail for now
Remove any existing deposit percentage or discount display from the tour detail sidebar.
Do not add deposit/discount fields to the new tour form.
Will be addressed in T19 (payments).

---

## 2. Tour detail sidebar — widen to 380px
Change sidebar column width from 320px to 380px in .page-body grid.
Do not remove content. The extra width reduces vertical scroll.
Move "Request private dates" section below the sticky sidebar column so it does not add to sidebar height.

---

## 3. Operator landing page nav — remove both links
Remove both "Apply as a guide" AND "How it works" from the operator.html nav bar.
Nav should only have logo + Sign in button.
Primary CTA stays in the hero section only.

---

## 4. Report this listing — send email
"Report this listing" on tour detail page should POST to /api/v1/contact/ with type="report" and tour slug.
Email sent to pul_khanna@yahoo.co.in with subject "Listing report: [tour name]".
Show confirmation: "Thank you. We'll review this listing within 24 hours."

---

## 5. Send a message — open enquiry modal, not contact page
"Send a message" on tour detail page opens the existing enquiry modal pre-filled with subject "General enquiry about [tour name]". Does NOT redirect to the site contact page.
Test: modal opens, submits, operator sees it in dashboard Enquiries tab.

---

## 6. Request private dates — test end to end
Verify the full flow works: tourist opens modal, fills form, submits.
Saves to localStorage (pre-T21 fallback).
Operator sees the enquiry in dashboard Enquiries tab.

---

## 7. Reviews — See all / Collapse
Show first 3 reviews by default on tour detail page.
"See all X reviews" button expands to show all.
"Collapse reviews" button appears after expanding.
If no reviews yet: show "Be the first to review this tour."

---

## 8. Operator signup page (signup-operator.html) — full UI rewrite
Current broken behaviour: tabs stack instead of replace, mandatory fields don't block Next, no Back button, 50-char minimum on bio is excessive.

Fix:
- Only current step content visible. Others are display:none, not stacked.
- Step indicator at top shows Step 1 / 2 / 3 with active state.
- Clicking ahead in indicator only allowed if previous steps are complete.
- Next validates required fields in current step before advancing. Highlight red + inline error if missing. Do NOT advance until all pass.
- Back button on steps 2 and 3.
- Submit button on step 3 only.

Step 1 required: first name, last name, valid email, password (min 8 chars).
Step 2 required: at least one category selected. Remove the 50-char bio minimum entirely.
Step 3 required: all consent checkboxes ticked before Submit activates.

Email field: identical styling to all other fields. No special highlight or outline.

---

## 9. Operator signed in — show dashboard in nav, not Sign in
When waybound_user in localStorage has role=operator, the nav on ALL pages must show:
- Avatar with initials (or photo if uploaded)
- Dropdown with "Operator dashboard" as first item
Must NOT show: Sign in / Sign up or Apply as a guide buttons.

This is broken on: all pages except operator-dashboard.html itself.
Root cause: malformed Unicode escape in the nav dropdown HTML string (the dashboard icon \u1F4CA should be \uD83D\uDCCA or use the actual 📊 character).
Fix the nav IIFE in every page file. Test on: homepage, adventures, tour detail, settings, operator.html.

---

## 10. Operator dashboard nav icon — broken across site
The "📊" dashboard icon in the dropdown shows as "OA" or garbled on all pages except the dashboard.
Same fix as item 9 above — fix the Unicode escape in every nav block across all pages.

---

## 11. Profile photo — settings page
Three sub-issues:
- Upload not working: wire file input to PATCH /api/v1/auth/me/ as multipart/form-data. Backend needs MultiPartParser added to me() view. After upload, store photo_url in waybound_user localStorage.
- Remove option broken: PATCH /api/v1/auth/me/ with avatar=null. Revert nav to initials.
- Photo not showing in nav: after upload, all pages must show the photo in the nav avatar, not initials. Nav JS reads waybound_user.photo_url — ensure this is set after upload.

---

## 12. Property photos — optional per accommodation block (new tour form)
Each stay block in the accommodation section gets an optional "Add property photos" button (1-4 photos).
Backend: PropertyPhoto model with FK to StayBlock, image, order.
Endpoint: POST /api/v1/tours/<slug>/stays/<id>/photos/
Tour detail page: show property photos in accommodation section as horizontal scroll. Only if photos exist — no placeholder.

---

## 13. Use previous tour as template (new tour form)
Top of new tour form (only when no ?slug= param): show a one-line collapsed row:
"Start from a template: [dropdown of operator's previous tours] [Apply]"
No X/close button — row always stays visible. Hide row only if operator has no previous tours.
On Apply: fetch tour data, pre-fill all fields. Do NOT copy photos or departure dates. Append " (Copy)" to title.

---

## 14. Private tours — confirmed flow
Two separate features:

Tourist side (already exists): "Request private dates" enquiry modal on tour detail page. No change.

Operator side: After agreeing with a tourist (via enquiry or off-platform), operator creates a new tour with "Private listing" toggle ON.
- Private tour: status=live, is_private=True
- Does NOT appear on homepage or adventures (public list filters is_private=False)
- IS accessible via direct URL slug (no 404)
- My tours card shows 🔒 icon + "Copy link" button for private tours
- Operator shares link directly with the tourist

Backend: add is_private boolean to Tour model (default False). Update public list filter.

---

## 15. Booking page — back to tour link broken
"← Back to tour" link must go to tour_detail_page.html?slug=<slug> using the slug from URL params.
Currently leads to a broken/incomplete tour detail page. Pass slug correctly.

---

## 16. Contact page — email + cleanup
- Form submits to pul_khanna@yahoo.co.in via POST /api/v1/contact/ (Django send_mail)
- Mandatory fields: name, email, message — inline validation, no browser alerts
- Remove "International support" section entirely
- Success message: "Message sent. We'll get back to you within 24 hours."

