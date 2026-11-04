# Roles rubric (normative — derived from the study's gold conventions)

The `roles` feature is not "user types mentioned in the text." It is the
**canonical marketplace roles** the study tracks, after mapping surface
synonyms. Follow this table exactly.

## 1. Canonical mapping table

Map every person-type noun in the input through this table:

| Canonical role | Surface forms that map to it |
|---|---|
| `owner` | owner, seller, host, vendor, landlord, provider |
| `renter` | renter, guest, customer, buyer, client, patron |
| `admin` | admin, administrator, platform manager |

**Not mapped — drop them entirely:** staff, moderator, editor, user(s),
everyone, people, "both parties", any other noun not listed above.
(Example: "Staff can manage the platform" → `roles: []`. "Staff and admins
keep the platform safe" → `roles: [admin]` — staff drops, admin stays.)

## 2. Rules

1. `roles` = the sorted list of unique canonical names, **singular** form
   (`renters` → `renter`).
2. Any case with ≥ 1 mapped actor gets the roles feature ON and its list —
   even a single actor ("Hosts upload a profile photo" → `roles: [owner]`).
3. No mapped actor → roles OFF, empty list.
4. Never invent roles the text doesn't mention, and never keep an unmapped
   surface noun in the list.
5. `features.roles: true` exactly when the list is non-empty; record
   `roles.role_names` with the same list.

## 3. Worked examples (from the study corpus)

| Input (excerpt) | Correct annotation | Why |
|---|---|---|
| "Sellers upload photos of their property listings" | `roles: [owner]` | seller → owner |
| "Customers give feedback after each rental" | `roles: [renter]` | customer → renter |
| "Renters can request a booking and the owner approves" | `roles: [owner, renter]` | two mapped types |
| "A moderator can suspend listings" | `roles: []` | moderator not mapped |
| "Users can upload documents" | `roles: []` | "users" not mapped |
| "Staff and admins keep the platform safe" | `roles: [admin]` | staff drops, admin stays |

## 4. Why this rubric exists

An LLM annotator run under generic instructions could not reproduce the
gold's roles convention (Cohen's κ −0.84 under "named user types" wording,
−0.55 under "two types with different capabilities" wording; see
`tests/annotation/llm_annotator/RESULTS.md`). The convention is a
synonym-mapping table, not a linguistic rule — so the table is now stated,
not implied.
