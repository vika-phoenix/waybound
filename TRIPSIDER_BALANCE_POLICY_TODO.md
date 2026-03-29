# Balance Due & Cancellation Policy — Problem + TODO

## The Core Problem

`balance_due_days` is a single field on the Tour model (default = 30).
`balance_due_date` is calculated as: `departure_date - balance_due_days`

This causes multiple mismatches:

1. **balance_due_days = 30 doesn't align with cancellation policy tiers**
   - Default cancel policy: free cancellation at 30+ days, 50% penalty at 14–29 days
   - Balance is due exactly when tourist enters the 50% penalty zone
   - If tourist hasn't paid and operator cancels at this point, operator can only recover
     50% penalty but tourist only paid 30% deposit — operator can't recoup full penalty amount
   - balance_due should sit INSIDE the free cancellation window

2. **Last-minute bookings produce a balance_due_date in the past**
   - Tourist books 5 days before departure, balance_due_days = 30
   - balance_due_date = 25 days ago — already passed at booking time
   - System currently sets this broken date on the booking with no fallback
   - Tourist is immediately "overdue" before they even booked

3. **Single-day tours get same balance_due_days as 2-week expeditions**
   - 30 days balance window for a 1-day city walk makes no sense
   - A day tour might only be bookable 3–5 days out at most

4. **No alignment between tour length, cancel policy, and balance window**
   - All three should relate to each other but are currently independent settings
   - Operator has no guidance on what values make sense together


## Suggested Sensible Defaults (by tour length)

| Tour length  | Cancel-free window | balance_due_days |
|--------------|--------------------|------------------|
| 1 day        | 7+ days            | 5 days           |
| 2–7 days     | 14+ days           | 10 days          |
| 8–14 days    | 21+ days           | 21 days          |
| 15+ days     | 30+ days           | 30 days          |

balance_due_days should always fall inside the cancel-free window so tourist
can still get a full refund if they haven't paid yet.


## TODO — Changes Required

### 1. Backend fix (payments/views.py) — HIGH PRIORITY
- When calculating balance_due_date, if result <= booking_date (i.e. in the past
  or same day), charge 100% upfront instead of deposit split
- Set balance_due_date = None in this case (no balance owed)
- This fixes last-minute booking edge case cleanly

### 2. Backend — smart balance_due_days default
- When operator hasn't set balance_due_days (or value is default 30), derive
  a sensible default from tour.days at booking time
- Do NOT change the field on the tour itself — compute per booking

### 3. Tour create form (operator-tour-create.html)
- Add balance_due_days field (currently missing from form entirely)
- Show it with a plain label: "Collect full payment X days before departure"
- Pre-fill based on tour.days as a suggestion (not dynamic — fill on load only)
- Add cancellation policy preset templates: Flexible / Moderate / Strict
  so operator isn't building policy from scratch
- Show a note linking policy tiers to balance_due_days:
  "Balance should be due while tourists can still cancel for free"

### 4. Tour detail page — booking section
- Show balance_due_days in plain language near the cancellation policy widget
  e.g. "Full payment required 21 days before departure"
- Currently cancellation policy tiers are shown but payment schedule is not
- Tourist should see both before booking: when deposit is due and when balance is due

### 5. Booking confirmation email + page
- Make balance_due_date prominent in confirmation:
  "Your deposit of X is confirmed. Remaining Y must be paid by [date]."
- Currently it's included but not highlighted enough

### 6. Reminder emails — update message content
- Tourist balance reminders (14d, 7d, 3d) should include:
  - The cancellation policy at that point ("if you cancel now you get X% back")
  - What happens if balance not paid ("your spot may be released")
  - Contact operator link if they have an arrangement
- Operator balance reminders should include:
  - Days until next penalty tier escalation (already partly there)
  - Reminder that they can cancel and keep penalty amount
  - Link to dashboard to action the booking

### 7. Terms of use / FAQ
- Add a clear section explaining the deposit + balance split to tourists
- Explain what happens if balance not paid (operator can cancel, policy applies)
- Explain that last-minute bookings require full payment
- Operators: explain that cancelling a ghost tourist applies the cancellation
  policy in their favour (once fix #1 above is built)

### 8. Operator cancellation logic fix (bookings/views.py) — HIGH PRIORITY
- Currently when operator cancels ANY booking, tourist gets 100% refund
- Should be: if cancellation reason is unpaid balance / tourist ghost,
  treat as tourist-fault cancellation and apply cancellation policy
- Operator keeps penalty % from whatever was paid
- Requires operator to select a reason when cancelling
  (e.g. "Tourist did not pay balance" vs "I cannot fulfil this booking")
  - "Cannot fulfil" → full refund to tourist (operator's fault)
  - "Tourist did not pay" → policy applies (tourist's fault)


### 9. Slot display — "On Hold" count (tour detail page)
- Currently spots_left counts ALL confirmed bookings (deposit-only + fully paid)
- Better: split into confirmed (fully paid) vs on hold (deposit only, balance pending)
- Show tourists: "3 spots left (1 on hold)" so they know real availability
- This acts as a natural soft overbooking buffer — operator can accept slightly
  more bookings knowing some on-hold slots will drop off if balance not paid
- No actual overbooking needed — just honest slot visibility
- Requires: backend spots_left calculation to split by balance_status,
  frontend tour detail page to show the on-hold count separately


## Not Building (decided against)

- Auto-cancel on balance_due_date — too aggressive, breaks operator-tourist
  verbal agreements. Operator must manually cancel.
- Hard overbooking system (accepting more bookings than max_group) — complex,
  risk of double-confirming. The on-hold slot display (TODO #9) achieves the
  same outcome naturally without actually exceeding capacity.
