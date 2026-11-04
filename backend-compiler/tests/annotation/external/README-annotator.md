# Backend annotation task — annotator instructions

You are annotating 50 short natural-language descriptions of web-app
backends. Each one asks for a system like "an Airbnb where hosts approve
each booking." Your job: read each description and record **only what the
text actually says** — never what seems plausible or implied.

**Budget: ~4 minutes per case; total 3–4 hours.** Flag anything that takes
longer in the `notes:` field.

## What you fill in

One file per case, in `worksheets/held_out/` **first**, then
`worksheets/golden/`. Each file looks like this:

```yaml
case: booking_mode_request_then_approval
input: '...'            # already filled — do not change
features: {}            # YOU FILL: feature name -> true or false
parameters: {}          # YOU FILL: parameter name -> value (only if pinned by the text)
roles: []               # YOU FILL: named user types (e.g. [host, guest])
buckets: []             # YOU FILL: file-upload purposes (e.g. [avatars])
edge_functions: []      # leave empty unless the text explicitly describes a webhook/server function
notes: ""               # anything ambiguous, in your own words
```

## The 10 features (use these exact names, lowercase)

| Feature | Turn it on when the text describes... | Parameter (only if the text pins it) |
|---|---|---|
| `authentication` | users signing in / accounts | `authentication.method`: `email_password`, `magic_link`, `oauth_google`, `oauth_github` |
| `roles` | distinct named user types (host/guest, admin/moderator) | `roles.role_names`: the list of names as written |
| `bookings` | reserving/bookings/scheduling of items | `bookings.mode`: `instant`, `owner_approval`, `request_then_approval`, `time_slot` |
| `messaging` | users sending messages to each other | `messaging.trigger_event`: `before_booking`, `after_request`, `after_approval`, `anytime` |
| `payments` | charging money / checkout / cards | `payments.provider`: `stripe` |
| `reviews` | ratings/reviews of listings after stays | (no parameter) |
| `file_storage` | uploading files/photos/documents | `file_storage.bucket_purpose`: `avatars`, `listings`, `documents`, `mixed` |
| `verification` | identity/verification checks | `verification.method`: `email`, `phone`, `government_id`, `admin_approval`, `government_id_and_admin` |
| `realtime` | live/instant updates pushed to users | `realtime.channels`: any of `messages`, `notifications`, `bookings` (list) |
| `favorites` | saving/bookmarking items | (no parameter) |

`roles:` at top level duplicates `roles.role_names` — fill both the same way.

## The rules (these decide whether the study is valid)

1. **Silent = omit.** If the text doesn't mention something, do NOT add it —
   leave it out of `features` entirely. Omission is a judgment that matters;
   a missing feature means "should be off."
2. **Forbidden = false.** If the text explicitly rejects something ("no
   payments, cash on arrival only"), write `payments: false`.
3. **Don't infer.** "Guests can review" → `reviews: true` (stated).
   "An Airbnb clone" alone → do NOT add bookings/payments unless described.
4. **Contradictions:** record both readings in `notes:`, pick the more
   conservative one, move on. Do not ask the authors — independence is the
   point.
5. **Only fill from the text.** Do not run the tool, read the repo's other
   files, or search for the "right" answers.
6. **Edit only your copy.** Return the whole `external/` folder with your
   filled files; change nothing else in the repository.

## When you're done

Return the folder as a zip. You will NOT be told which answers "matched" —
by design. Questions about mechanics (not meaning) only:
contact the study coordinator.
