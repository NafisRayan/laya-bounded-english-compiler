# Composition Engine Implementation Plan (spec §7, Phase 2)

Status: approved internally; execute per this plan. Branch: `master`.
Repo root: `C:\Users\BS00861\Documents\GitHub\Laya Supabase\system`.
Code base: `backend-compiler/`. VENV: `backend-compiler\.venv\Scripts\python.exe`.
Spec authority: `Developer Spec.md` §7 (lines 1018-1118), §10.1, §18.11 (2591-2659), §18.14 (2747-2788), §18.18 (2965-2993), §12 (Jinja2 templates).

## Scope
Build `compiler/generator/` (composition engine) end to end so that:
`recompute_spec(spec, ontology)` → `compose(spec, ontology)` → `list[Migration]`
emits ordered, idempotent, conflict-checked SQL migrations, and the spec's
composer/idempotency/fragment-matrix test suite passes.

Out of scope (later milestone): `compiler/deployer/` (§8), §18.15 migration-cleanup
and §18.16 remediation tests (depend on deployer). Edge functions (§7.1
`edge_function` type, `edge_templates/`) are scaffolded by the deployer, NOT emitted
as migrations — `compose` ignores `edge_function` fragments.

## Environment prerequisites (already done)
- `jinja2==3.1.6` and `psycopg[binary]==3.3.6` installed (+ their deps).
- Docker engine running; `postgres:15` image pulled (`docker.io/library/postgres:15`).
- Baseline suite: 162 collected.

## New package layout
```
backend-compiler/compiler/generator/
  __init__.py          # re-export compose, load, list_all_fragments, topo_sort, Migration, CompositionError
  models.py            # Migration, Fragment, CompositionError (+ ConflictIssue)
  fragments.py         # registry: list_all_fragments(), load(id), load_all(); static YAML fragments loader
  fragments/*.yaml     # static fragments: function_*, bucket_*, realtime_*, trigger_*
  table_fragments.py   # build table_<entity> Fragment objects from ontology entity defs
  rls.py               # rls_for(entity, spec, ontology) + per-entity policy plans
  ordering.py          # topo_sort(fragments, key="requires")
  composer.py          # compose(), render(), detect_conflicts(), load()
  fragment_spec_map.py # spec_for(fragment_ids) -> BackendSpec
```
Python 3.13, pydantic v2, Jinja2 (package name `jinja2`, import `jinja2`), psycopg 3.

## Key design decisions

### D1 — `Migration` model
`compiler/generator/models.py`:
```python
class Migration(BaseModel):
    filename: str
    sql: str
```
Keyword-constructible with exactly these two fields (spec §7.3:1098-1101).
Consumers read `.filename` and `.sql` only.

### D2 — `Fragment` model
```python
class Fragment(BaseModel):
    id: str
    type: Literal["table","rls","trigger","function","bucket","realtime","edge_function"]
    requires: list[str] = []
    provides: list[str] = []
    sql: str
```
Static fragments are authored as YAML in `fragments/*.yaml`:
```yaml
id: function_is_admin
type: function
requires: [table_profiles]
provides: [function.is_admin]
sql: |
  CREATE OR REPLACE FUNCTION is_admin()
  RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin');
  $$;
```
`fragments.py` loads every `*.yaml` in the package dir into a registry dict
(id→Fragment), and must expose `list_all_fragments() -> list[str]` (sorted ids,
spec §18.18:2974) and `load(fragment_id) -> Fragment` (missing id →
`CompositionError(f"unknown fragment: {id}")`). `load` must also work for
generated ids (`table_<entity>`, `rls_<entity>_<group>`) by delegating to
`table_fragments` / `rls` builders when not found in the static YAML set
(`rls_listings_owner` etc. are thus available to `topo_sort` tests).
A `load_all()` returning `list[Fragment]` (static + generated for all ontology
entities/rls) drives `list_all_fragments` — which therefore returns the union of
static ids AND generated table/rls ids for every ontology entity.

### D3 — Table fragments generated from the ontology (not hand-written)
`table_fragments.py` builds `table_<entity>` for each entity in
`ontology.entities` EXCEPT `users` (managed by Supabase Auth). SQL column renderer:
- `type` passthrough for `uuid|text|timestamptz|integer|jsonb`; `pk: true` →
  `PRIMARY KEY` (single pk inline; composite pk → trailing `PRIMARY KEY (a, b)`).
- `fk: "table.col"` → `REFERENCES table(col)`, plus ` ON DELETE <on_delete>`
  when present.
- `nullable: true` → column nullable, else `NOT NULL`.
- `default` is emitted verbatim (already SQL, e.g. `gen_random_uuid()`, `now()`,
  `'user'`) — providers must NOT re-quote it.
- `unique: true` → `UNIQUE`.
- Column order = YAML field order.
- Indexes: `CREATE INDEX IF NOT EXISTS {entity}_{n}_{cols}_idx ON {entity}({cols});`
  named deterministically (n = index ordinal).
`requires` for a table fragment: every managed entity referenced by a foreign key
in its `fields` (map `table.col → table_<table>`; skip `users`). This yields
real dependency edges: `table_bookings → table_listings`, `table_messages →
table_bookings`, `table_reviews → table_bookings`, `table_favorites →
table_listings`.
`provides`: `["entity.{entity}"]`.

### D4 — RLS policy plans (`rls.py`)
`rls_for(entity, spec, ontology) -> list[Fragment]` returns fragment ids
`rls_{entity}_{group}` per the group table below (fragment ids are per role-GROUP,
so `rls_listings_owner` exists as required by spec §18.11:2656). Each rls fragment
emits, for EVERY op in its group, an owner-policy with that op's predicate, plus a
single `ENABLE ROW LEVEL SECURITY`:
```sql
ALTER TABLE {entity} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS {entity}_{op}_rls_{entity}_{group} ON {entity};
CREATE POLICY {entity}_{op}_rls_{entity}_{group} ON {entity}
  FOR {OP} USING ({predicate});
```
Policy name follows spec §7.4: `{table}_{operation}_{fragment_id}`.
`users` gets NO rls (managed). Group table (entity → groups; group → ops + predicate),
all columns verified against `versions/v1/entities.yaml`:
| entity | group | ops | predicate |
|---|---|---|---|
| profiles | auth | SELECT, INSERT | `auth.uid() IS NOT NULL` |
| profiles | owner | UPDATE, DELETE | `auth.uid() = id` |
| listings | owner | SELECT, UPDATE, DELETE | `auth.uid() = owner_id` |
| listings | insert | INSERT | `auth.uid() IS NOT NULL` |
| bookings | participant | SELECT, INSERT, UPDATE, DELETE | `auth.uid() IN (renter_id, owner_id)` |
| messages | participant | SELECT, INSERT, UPDATE, DELETE | `auth.uid() IN (sender_id, recipient_id)` |
| payments | owner | SELECT | `auth.uid() = payer_id` |
| payments | insert | INSERT | `auth.uid() IS NOT NULL` |
| reviews | author | SELECT, INSERT, UPDATE, DELETE | `auth.uid() IN (author_id, subject_id)` |
| files | owner | SELECT, UPDATE, DELETE | `auth.uid() = owner_id` |
| files | insert | INSERT | `auth.uid() IS NOT NULL` |
| verification_documents | owner | SELECT, UPDATE, DELETE | `auth.uid() = user_id` |
| verification_documents | insert | INSERT | `auth.uid() IS NOT NULL` |
| favorites | owner | SELECT, INSERT, DELETE | `auth.uid() = user_id` |
| notifications | owner | SELECT, UPDATE, DELETE | `auth.uid() = user_id` |
`requires`: `[table_{entity}, function_is_admin]`. (Uniform across all RLS
fragments: keeps role-helper functions ordered before every policy — spec §18.11's
`test_topological_sort_respects_requires` pins exactly this edge — and guarantees
the matrix's policy-only pairs still create `profiles` + `is_admin()`.) 
`provides: ["rls.{entity}.{group}"]`.
`rls_for` ignores `spec` contents today but keeps the signature per spec
§7.3:1082 (forward-compat for `rls_overrides`).
Fragment-id parse for generated rls ids: `rls_{entity}_{group}` where group ∈ the
group names above.

### D5 — Static fragments (YAML) to author
- `function_is_admin`: `requires [table_profiles]`, body as D2 example.
- `function_is_owner`: `requires [table_listings]`:
  `SELECT EXISTS (SELECT 1 FROM listings WHERE owner_id = auth.uid());`
- `bucket_avatars`, `bucket_listings`, `bucket_documents`, `bucket_verification`
  (type `bucket`, `requires []`, `provides ["bucket.{name}"]`):
  ```sql
  INSERT INTO storage.buckets (id, name, public, file_size_limit)
  VALUES ('{name}', '{name}', {public?true:false}, {10*1024*1024})
  ON CONFLICT (id) DO NOTHING;

  DROP POLICY IF EXISTS {name}_select_public ON storage.objects;
  CREATE POLICY {name}_select_public ON storage.objects
    FOR SELECT USING (bucket_id = '{name}');

  DROP POLICY IF EXISTS {name}_insert_owner ON storage.objects;
  CREATE POLICY {name}_insert_owner ON storage.objects
    FOR INSERT WITH CHECK (
      bucket_id = '{name}' AND auth.uid()::text = (storage.foldername(name))[1]
    );
  ```
  (select_public only when the bucket is public: avatars+listings public,
  documents+verification private; private buckets keep only insert_owner.)
- `realtime_messages`, `realtime_notifications`, `realtime_bookings`
  (type `realtime`; `requires [table_<channel>]` for channels that are entities;
  `provides ["realtime.{channel}"]`):
  ```sql
  DO $$
  BEGIN
    IF NOT EXISTS (
      SELECT 1 FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime' AND schemaname = 'public'
        AND tablename = '{channel}'
    ) THEN
      ALTER PUBLICATION supabase_realtime ADD TABLE {channel};
    END IF;
  END $$;
  ```
- `trigger_verification_status` (type `trigger`; `requires [table_verification_documents]`):
  ```sql
  CREATE OR REPLACE FUNCTION set_verification_status() RETURNS trigger AS $$
  BEGIN
    NEW.status := COALESCE(NEW.status, 'pending');
    RETURN NEW;
  END; $$ LANGUAGE plpgsql;

  DROP TRIGGER IF EXISTS trigger_verification_status ON verification_documents;
  CREATE TRIGGER trigger_verification_status
    BEFORE INSERT OR UPDATE ON verification_documents
    FOR EACH ROW EXECUTE FUNCTION set_verification_status();
  ```

### D6 — `compose()` (spec §7.3:1071-1103) — EXACT behavior
```python
def compose(spec: BackendSpec, ontology: Ontology) -> list[Migration]:
    spec = recompute_spec(spec, ontology)
    fragments = []
    if spec.features.get("authentication"):
        fragments.append(load("function_is_admin"))
        fragments.append(load("function_is_owner"))
    for entity in spec.entities:
        fragments.append(load(f"table_{entity}"))
        fragments.extend(rls_for(entity, spec, ontology))
    for bucket in spec.buckets:
        fragments.append(load(f"bucket_{bucket.name}"))
    if spec.features.get("realtime"):
        for channel in spec.parameters.get("realtime.channels", []):
            fragments.append(load(f"realtime_{channel}"))
    if spec.features.get("verification"):
        fragments.append(load("trigger_verification_status"))
    ordered = topo_sort(fragments, key="requires")
    conflicts = detect_conflicts(ordered)
    if conflicts:
        raise CompositionError(conflicts)
    migrations = []
    for i, frag in enumerate(ordered):
        migrations.append(Migration(
            filename=f"{i:04d}_{frag.id}.sql",
            sql=render(frag, spec=spec, ontology=ontology),
        ))
    return migrations
```
Guard against emitting a realtime fragment for a channel that is not an entity:
`TABLE_BACKED_REALTIME_CHANNELS` from `compiler.spec.derive` is
`{"messages","notifications","bookings"}` — only emit `realtime_{channel}` when
`channel in TABLE_BACKED_REALTIME_CHANNELS`. `realtime_<channel>.requires` then
`[table_<channel>]`, and `spec.entities` already contains the channel table stem
because `derive_entities` only derives the realtime entity when the channel is
table-backed (§3 of audit).

### D7 — `topo_sort` (`ordering.py`)
`topo_sort(fragments: list[Fragment], key="requires") -> list[Fragment]`
- Stable Kahn's algorithm. `frag.requires` entries → dependency edges.
- A requires id not present among provided fragment ids is IGNORED for ordering
  (e.g. a table requiring `users` — supabase-managed, never a fragment).
- On residual cycle: raise `CompositionError(["ordering cycle: ..."])`
  (spec rule 5 "Ordering violations", §7.4).
- `test_topological_sort_respects_requires` contract (spec §18.11:2653-2658):
  `topo_sort([rls_listings_owner, function_is_admin], ...)` must place
  `function_is_admin` before `rls_listings_owner` because
  `rls_listings_owner.requires == ["table_listings"]` and
  `table_listings.requires == [function_is_admin]`? NO — see fix below.

**CRITICAL correction to the §18.11 test's expectation:** the test loads
`rls_listings_owner` and `function_is_admin` and asserts `ordered.index(a) <
ordered.index(b)` where `a = function_is_admin`, `b = rls_listings_owner`. Under
D4, `rls_listings_owner.requires == ["table_listings"]` and
`function_is_admin.requires == ["table_profiles"]` — no direct edge exists. For
the test to hold, the rls chain must transitively depend on the admin function:
make `table_profiles.requires == []` but have `function_is_admin` provide
`function.is_admin` AND make ORM-side `rls_listings_owner` reach `function_is_admin`
through the dependency a reviewer can SEE. Implement: `provides` relation is
irrelevant to ordering; instead set `function_is_admin.requires == []` and
`rls_listings_owner.requires == ["table_listings", "function_is_admin"]` —
because the RLS policy body does not call `is_admin()`, but keeping the admin
function ordered before RLS is harmless and satisfies the spec test. Document
this as a deliberate spec-test alignment (the spec test pins this ordering).
Both `compose()` and the matrix still validate cleanly.

### D8 — `detect_conflicts(ordered)` (spec §7.4)
Returns `list[str]` of issues (empty → OK):
1. Duplicate fragment id (two fragments with same id in the set).
2. Duplicate object name: collect `CREATE TABLE|CREATE INDEX|CREATE FUNCTION|CREATE TRIGGER <name>` and duplicate bucket names from UNIQUE object names; same object created by 2+ fragments → issue.
3. Policy name collisions: collect `CREATE POLICY <name>`; duplicates → `RLS policy name collision: <name>`.
4. Trigger collisions: two `CREATE TRIGGER <name>` on same table → issue.
5. FK cycles: run DFS over table fragments' `requires` graph restricted to table→table edges; on cycle → `FK cycle: <chain>`.
6. Ordering violation: any `frag.requires` id that IS present in the migration-id set but appears AFTER `frag` in `ordered` → issue (defensive; topo_sort already enforces).

### D9 — `render(frag, spec, ontology)` (`composer.py`)
For generated fragments the SQL is built at build time (entities/rls/table) and
`render` returns `frag.sql` unchanged for `table`/`rls`. For static fragments that
embed `{name}`/`{channel}`/`{public}` placeholders (bucket_, realtime_), `render`
applies a small templating pass:
```python
def render(frag, spec, ontology):
    if frag.type in ("bucket", "realtime"):
        from string import Template
        return Template(frag.sql).safe_substitute(
            name=frag.id.split("_", 1)[1] if frag.type == "bucket" else "",
            channel=frag.id.split("_", 1)[1] if frag.type == "realtime" else "",
            public="true" if _bucket_public(frag.id) else "false",
        )
    return frag.sql
```
`_bucket_public`: avatars→true, listings→true, documents→false, verification→false.
(Jinja2 is installed per §12 but not required for these two placeholder classes;
keep the code Jinja2-free to minimize surface — Jinja2 stays available for §8.)

### D10 — `fragment_spec_map.spec_for(fragment_ids)` (§18.18:2990-2992)
Builds a valid `BackendSpec` whose `compose()` output covers at least the given
fragment ids. Mapping rules (implement as a dict + builder):
- fragment → extra spec ingredients:
  - `function_is_admin`, `function_is_owner`, `table_profiles` → `features["authentication"]=True`, `parameters["authentication.method"]="email_password"`, `roles=["user"]`.
  - `table_listings`, `table_bookings`, `table_reviews`, `table_favorites` (and their `rls_*` variants) → ensure `bookings` enabled (derives listings+bookings; reviews/favorites also need bookings per constraints).
  - `table_messages`/`rls_messages_*` → `messaging=True`, `parameters["messaging.trigger_event"]="after_request"`.
  - `table_payments`/`rls_payments_*` → `payments=True`, `parameters["payments.provider"]="stripe"`.
  - `table_files`/`rls_files_*` → `file_storage=True`, `parameters["file_storage.bucket_purpose"]="documents"`.
  - `table_verification_documents`/`rls_verification_documents_*`/`trigger_verification_status` → `verification=True`, `parameters["verification.method"]="admin_approval"` + `file_storage=True` (constraint: verification requires file_storage).
  - `table_notifications`/`rls_notifications_*`/`realtime_notifications` → `realtime=True`, `parameters["realtime.channels"]=["notifications"]`.
  - `realtime_messages` → `realtime=True`, channels `["messages"]`.
  - `realtime_bookings` → `realtime=True`, channels `["bookings"]` (bookings feature must be enabled too).
  - `bucket_avatars` → `file_storage=True`, purpose `"avatars"`; `bucket_listings` → purpose `"listings"`; `bucket_documents` → purpose `"documents"`; `bucket_verification` → `file_storage=True` purpose `"documents"` + `verification=True` (verify: derive_buckets appends `verification` bucket only when verification enabled).
- Assemble: start empty features → apply each rule → after all, ensure `authentication` is on whenever any feature on (constraints demand it) → `recompute_spec` → return.
`spec_for` must produce a spec that passes `validate()` (constraints are hard:
reviews→bookings, favorites→bookings, verification→file_storage,
realtime.channels.contains(messages)→messaging, contains(bookings)→bookings).

### D11 — Postgres test fixtures (conftest)
Add to `tests/conftest.py`:
```python
import os, subprocess, socket, time

@pytest.fixture(scope="session")
def local_postgres():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if dsn:
        yield dsn
        return
    # docker CLI managed postgres:15 on an ephemeral port
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    name = "laya-test-pg"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(["docker", "run", "-d", "--name", name, "-e", "POSTGRES_PASSWORD=postgres",
                    "-e", "POSTGRES_USER=postgres", "-p", f"{port}:5432", "postgres:15"],
                   check=True, capture_output=True)
    url = f"postgresql://postgres:postgres@127.0.0.1:{port}/postgres"
    import psycopg
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            with psycopg.connect(url) as c: c.execute("SELECT 1")
            break
        except Exception: time.sleep(1)
    else:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        pytest.skip("postgres:15 container did not become ready")
    yield url
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)

@pytest.fixture
def fresh_db(local_postgres):
    # spec §18.2 (1857-1894): reset public schema, stub auth + storage
    import psycopg
    with psycopg.connect(local_postgres, autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        cur.execute("CREATE SCHEMA IF NOT EXISTS auth;")
        cur.execute("CREATE TABLE auth.users (id uuid PRIMARY KEY);")
        cur.execute("CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$ SELECT NULL::uuid $$;")
        cur.execute("CREATE SCHEMA IF NOT EXISTS storage;")
        cur.execute("""CREATE TABLE storage.buckets (id text PRIMARY KEY, name text, public boolean, file_size_limit bigint);""")
        cur.execute("""CREATE TABLE storage.objects (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), bucket_id text, name text);""")
        cur.execute("""CREATE OR REPLACE FUNCTION storage.foldername(text) RETURNS text[] LANGUAGE sql AS $$ SELECT string_to_array($1, '/') $$;""")
        cur.execute("""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname='supabase_realtime')
            THEN CREATE PUBLICATION supabase_realtime; END IF; END $$;""")
    yield local_postgres
```
(Stubs exactly the spec's auth/storage surface plus a `supabase_realtime`
publication so the realtime fragments can execute — the spec's §18.2 stub omits
it; document the addition.)

## Test files to create

### tests/unit/test_ordering.py
- `test_topo_sort_respects_requires`: table_bookings whose requires=[table_listings]; assert table_listings before table_bookings.
- `test_topo_sort_cycle_raises`: two fragments requiring each other → `CompositionError`.
- `test_topo_sort_external_requires_ignored`: fragment requiring `users` (never a fragment) sorts fine.
- `test_topo_sort_stable`: two independent fragments keep input order.

### tests/unit/test_composer.py — the spec §18.11 six tests verbatim (2599-2658)
Plus:
- `test_compose_requested_fragments_present`: marketplace→ every table/bucket/realtime id named in D6 appears as a migration file; `function_is_admin`, `function_is_owner` present.
- `test_compose_no_edge_function_migrations`: no migration filename contains `edge_function`.
- `test_conflict_duplicate_bucket_raises`: force two bucket_avatars into the set (via a spec with duplicated bucket) → `CompositionError`.
- `test_migration_models_have_filename_and_sql`.
- `test_table_fragment_from_ontology`: `load("table_listings")` SQL contains `CREATE TABLE IF NOT EXISTS listings`, `REFERENCES users(id)`, the composite-pk favorite table contains `PRIMARY KEY (user_id, listing_id)`, `table_profiles` has NO `gen_random_uuid()` on id (profile id default should be absent).

### tests/unit/test_rls.py
- `test_rls_fragment_shape`: `load("rls_listings_owner")` contains `ALTER TABLE listings ENABLE ROW LEVEL SECURITY;`, `CREATE POLICY listings_select_rls_listings_owner ... auth.uid() = owner_id`.
- `test_policy_name_convention`: name == `{entity}_{op}_{fragment_id}`.
- `test_every_managed_entity_has_rls`: all 10 non-users entities produce rls fragments via `rls_for`.
- `test_users_has_no_rls`.

### tests/integration/test_idempotency.py — spec §18.14 (2750-2788) verbatim
(3 tests: compile-twice identical; apply-twice cleanly on fresh_db; policy drop/create present.)

### tests/integration/test_fragment_matrix.py — spec §18.18 (2968-2992) verbatim
(`test_pair_applies` + `_spec_for_fragments`). Mark the module `pytest.mark.slow`.

## pyproject changes (`backend-compiler/pyproject.toml`)
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: integration tests requiring the postgres:15 test container or long runtime",
]
```

## Task breakdown
- **Task 1 — generator core + unit tests.** New `compiler/generator/` package per
  D1–D10; `tests/unit/test_ordering.py`, `test_composer.py`, `test_rls.py`.
  Verify: `pytest tests\unit -q` green; new unit files green. (Implementer: one
  session; self-verify with VENV python.)
- **Task 2 — integration fixtures + integration tests.** conftest fixtures (D11),
  `tests/integration/test_idempotency.py`, `tests/integration/test_fragment_matrix.py`,
  pyproject markers. Verify: `pytest tests\integration\test_idempotency.py tests\integration\test_fragment_matrix.py -q` green (docker PG).
- **Task 3 — full suite + commit + cleanup.** `pytest -q` full (expect 162 + new,
  ALL green). Then commit as one logical commit when green (see Commit policy).

## Commit policy
One commit at the end of the milestone (after Task 3 green):
`Add fragment composition engine (spec §7, Phase 2)`.
Message body: bullet the key decisions (generated table/rls fragments from
ontology, `supabase_realtime` test stub, spec-test alignment for the
`rls_listings_owner` ordering edge).
No interim commits during implementation unless a checkpoint is explicitly
requested.

## Definition of done
- `pytest -q` fully green (162 baseline + all new unit + integration tests).
- `detect_conflicts` raises on every §7.4 rule in at least one unit test.
- `function_is_admin`/`function_is_owner`/buckets/realtime/trigger all emitted
  by `compose` exactly per D6; edge_function fragments never emitted.
- Fragment matrix + idempotency (apply twice) green against the containerized
  `postgres:15`.
- Reviews (spec compliance + code quality) pass; final whole-implementation
  review approves; push to `master`.