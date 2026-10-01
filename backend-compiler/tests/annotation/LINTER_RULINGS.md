# No-anchor linter rulings — adjudicator of record

Scope: all 136 NO_ANCHOR candidates in `anchor_lint_human.txt`, each reviewed
against its input sentence. Engine-gold report (`anchor_lint_engine.txt`) is
audit-only — no rulings apply to it.

Sync check first: the −5 adjudication sync (3 webhooks + marketplace
`mixed`/`documents`) verified exact against `human_gold.yaml`; no collateral
changes.

## Standing rules applied

1. **Record precedence.** Rows the 77-row adjudication already settled keep
   their outcome (both-defensible ⇒ annotation side stays in gold).
2. **Vocabulary standard.** An item is anchored iff the sentence contains the
   concept's own words or a routine morphology/synonym of them
   (book→bookings, pay/charge→payments, verify→verification,
   live/real time→realtime, message→messaging, whenever→anytime,
   bookmark→favorites, feedback→reviews, upload/photo/document/store→
   file_storage, list/item-photo→listings, profile photo→avatars,
   sign in/up/login/password/oauth→authentication).
3. **Edge functions are below the sentence's abstraction level.** No input in
   the corpus mentions webhooks, dispatch, callbacks, or edge infrastructure.
   `stripe`/`verification`/`notification` anchor features and parameters, not
   mechanisms. (Same principle as the adjudicated webhook drops.)

## Batch rulings — 82 keep / 54 drop

| Batch | Ruling | Basis / exceptions |
|---|---|---|
| `features authentication:True` ×45 | **keep 6, drop 39** | Keep only where the sentence has auth vocabulary: `alias_and_phrase_decide`, `laya_high_decides` ("email password for login"), `github_auth_alias`, `oauth_google_alias` ("sign in … auth"), `magic_link_alias` ("Login"), `bucket_purpose_avatars` ("sign up" — judgment call: registration act is auth-naming). Drop the other 39: no sentence mentions login/account creation. This is the single biggest agreement-bias population. |
| `features file_storage:True` ×13 | **keep all** | Every flagged case has upload/store/photo/document vocabulary (`upload a profile photo`, `stores avatars…`, `checks every id document`). Linter gap: tokens checked were file/storage only. |
| `features bookings:True` ×12 | **keep 11, drop 1** | Keep where book/booking/rent/rental/stay appears (`duplicate_phrase`, `marketplace`, `fully_answered`, `kitchen_sink`, `laya_high_enables_everything`, `negation_no_payments`, `negation_no_reviews`, `payments_and_uploads` "rent", `reviews_and_favorites` "stay", `feedback_word_reviews` "rental", `unparsed_sentence_resolved_feature`). **Drop** `saved_items_favorites` ("Shoppers keep saved items…" — no booking vocabulary). |
| `features roles:True` ×10 | **keep all** | Every flagged sentence names a privileged actor (admins/staff/moderator/senior team); the app distinguishes user types. Matches the adjudicated `contradiction_*` rows. |
| `features verification:True` ×6 | **keep all** | id check / verify / checks id documents in every flagged input. Linter gap: verify→verification. |
| `features payments:True` ×4 | **keep all** | charge/pay in every flagged input. Linter gap: pay/charge→payment. |
| `features messaging:True` ×4 | **keep all** | contact/message/messages in every flagged input. Linter gap: message→messaging, contact→messaging. |
| `features realtime:True` ×4 | **keep all** | "live updates"/"update live"/"real time" in every flagged input. Linter gap: live/real time→realtime. |
| `features favorites:False` ×1 | **keep** | `favorites_negated_alone`: "skip the bookmark feature" — bookmark=favorites, negated. |
| `features favorites:True` ×1 | **keep** | `saved_items_favorites`: "saved items" clearly implies favorites. |
| `features verification:False` ×1 | **keep** | `kyc_avoided_negation`: "avoid KYC" — KYC=verification, negated. |
| `edge_functions verification_webhook` ×5 | **drop all** | No webhook/callback in any sentence. |
| `edge_functions stripe_webhook` ×2 | **drop all** | Payment intent ≠ webhook mechanism. |
| `edge_functions notification_dispatch` ×3 | **drop all** | Live updates/notifications name realtime behavior, not a dispatch function. |
| `buckets documents` ×4 | **keep all** | `id_check_verification`, `fully_answered` (adjudicated both-defensible — record stands); `kyc_government_id`, `kitchen_sink` (government id + uploads — same torn zone, annotation side stays). |
| `parameters bucket_purpose=mixed` ×3 | **keep all** | `fully_answered` (adjudicated); `bucket_purpose_mixed` ("stores avatars, listing photos, and personal documents" — directly described); `kitchen_sink` (photos + government id). |
| `parameters bucket_purpose=documents` ×2 | **keep all** | Same evidence as the documents buckets above. |
| `buckets listings` ×2 | **keep all** | `payments_and_uploads` (adjudicated: photos "of it"); `marketplace` ("list equipment", "photos of their gear"). |
| `parameters bucket_purpose=listings` ×1 | **keep** | `payments_and_uploads` — adjudicated record. |
| `parameters bucket_purpose=avatars` ×1, `buckets avatars` ×1 | **keep** | "profile photo" clearly implies avatar storage. |
| `roles owner` ×2 | **keep all** | sellers→owner (function-equivalent, like vendors→owner): `bucket_purpose_listings`, `kyc_government_id`. |
| `roles renter` ×2 | **keep 1, drop 1** | Keep `feedback_word_reviews` ("Customers … after each rental" — customers-of-rentals ≈ renters, defensible). **Drop** `saved_items_favorites` ("Shoppers" — no rental context; same distance as buyers→renter, which was adjudicated annotator-misread). |
| `roles admin` ×2 | **drop all** | `moderator_role` (sentence says moderator, not admin), `staff_role` (sentence says staff; matches adjudicated ruling). |
| `roles verifier` ×1 | **keep** | `role_names_two_roles`: "a senior team checks" — function-equivalent naming, defensible. |
| `parameters verification.method=admin_approval` ×1 | **drop** | `role_names_two_roles`: sentence says "senior team checks", never admin/approval — the value is ontology convenience, not sentence evidence. Verification feature stays on, method unpinned. |
| `parameters messaging.trigger_event=anytime` ×1 | **keep** | "whenever they want" = anytime. |
| `parameters realtime.channels=[messages]` ×1 | **keep** | `realtime_chat`: chat channel = messages. |

## Consistency directives — unflagged rows, same fate

The linter passed these via partial token matches, but the anchor names a
feature/param, not the mechanism (Standing rule 3). Drop them too:

- `stripe_webhook`: `fully_answered_no_questions`, `kitchen_sink_marketplace`,
  `marketplace_airbnb_equipment` (anchored on "stripe")
- `verification_webhook`: `bucket_purpose_documents`,
  `marketplace_airbnb_equipment` (anchored on "verification")
- `notification_dispatch`: `realtime_all_channels` (anchored on "notification")

Net effect: **human gold edge_functions becomes `[]` in every case.**

## Net effect on human gold

- 54 flagged drops + 6 consistency drops = **60 removals**
  (39 authentication, 16 edge_functions, 1 bookings, 1 renter, 2 admin,
  1 verification.method)
- 82 flagged items kept (linter vocabulary gaps or adjudicated record)
- Gold grows: nothing.

## For the linter (map v2 — keep passes honest before the paper audit)

add: sellers→owner, pay/pays/paid/charge→payment, book/booked→booking,
rent/rental/stay→booking (domain), verify/verified/checks-id→verification,
live/"real time"→realtime, message/contact→messaging,
whenever→anytime, bookmark/saved→favorites, feedback→review,
upload/photo/store/document→file_storage, list→listing, item→listing
(only with photo context). Also: anchor feature `authentication` on
login/sign-in/sign-up/password/oauth vocabulary.

## Flag for the team (no action in gold)

`moderator_role`: annotation wrote `roles: [admin]` + `role_names:
[moderator]` for "A moderator can suspend listings." After the admin drop,
the roles list is empty while the param carries moderator — check whether the
annotation meant roles: [moderator].
