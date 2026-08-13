# Product lockfile & slug-set drift — a mirrored artifact stops mirroring

**The class.** A hand-maintained (or derived-but-cached) artifact silently stops
tracking the real thing it mirrors: a product-slug literal, or a product's
`package-lock.json` snapshot of its own `package.json`. The drift is invisible
in dev (an already-populated `node_modules`, or a build that never exercises the
stale branch, masks the gap) and surfaces only in CI or a clean container build
— **after** the drifting change was already promoted. N=3 in one session
(2026-07-22) crossed the recurrence bar (`KB § PATTERNS/architect/project-execution.md`
§ DRY — N=3+ MUST formalize):

1. **`@dnd-kit/*`** — a `KanbanBoard` organ import landed in `seed/lib/frontend/src`;
   `check_framework_deps`'s hand-curated `FRAMEWORK_DEPS` list didn't know about
   it (fixed in `acfef9bb` by deriving `organ_transitive_deps` from a live scan
   of the organ source — see `test_check_framework_deps.py::TestOrganTransitiveDeps`).
2. **`recharts` + `@radix-ui/react-tabs`** — the IDENTICAL failure reappeared two
   days later when chart organs were promoted, breaking `npm ci` across **seven**
   products. `check_framework_deps`'s package.json-declaration check was green
   (the deps WERE declared) — the gap was one layer down: the products'
   `package-lock.json` snapshots of the seed package's own `package.json` never
   got refreshed, so a clean `npm ci` silently skipped installing the new dep.
3. **`ALL_SLUGS`** — `scripts/infra/build-and-push.sh` hardcoded the deployable
   product-slug set. `knowledge-extractor` (a real, on-disk, start.sh-registered
   product that was never added to the prod fleet) entered CI's
   changed-files-derived build-scope the moment it got a commit, failed the
   stale membership check, and the script's fatal `exit 2` killed the **entire**
   fleet image build — no image pushed for any product.

All three: **a mirrored artifact drifting from the real thing it mirrors,
discovered only in CI, after promotion.** Two sibling axes of the SAME class:
slug-set drift (this doc's second half) and lockfile↔package.json drift (first
half). Both are now gated **locally, at commit time** — not just in CI — because
"discovered in CI after promotion" is precisely the loop this doc exists to
close.

## Axis 1 — product lockfile ↔ seed/framework package.json drift

**Mechanism.** A clean `npm ci` (used by `.github/workflows/test.yml`'s
per-product frontend jobs) reads **ONLY** `package-lock.json` — it never
re-resolves from `package.json`, and it **fails loudly** if the two disagree
(that's the whole point of `ci` vs `install`). A product's lockfile carries a
cached snapshot of each `file:`-linked local package's own dependencies
(`seed/lib/frontend` → `@noctusai/lib`, `seed/framework/frontend` →
`@noctusai/seed`) — keyed by the **real relative path**
(`"../../../seed/lib/frontend"`) in the lockfile's `packages` dict, alongside a
`"link": true` alias at `node_modules/@noctusai/lib`. When the seed package's
own `package.json` grows a new dependency (an organ promotion), every
consuming product's lockfile snapshot goes stale until that product's
lockfile is individually refreshed. `check_framework_deps` cannot see this —
it only reads `package.json`, which already declares the dep correctly.

**Detection — `check_product_lockfile_dep_sync`** (`compliance.py`, severity
`high`). For every `products/*/frontend/package.json`, union `dependencies` +
`devDependencies`; for every dep that's both **declared** AND required
(`FRAMEWORK_DEPS` ∪ the live seed-organ transitive-import scan, reused from
`check_framework_deps._required_deps` — DRY, not a second derivation), assert
the sibling `package-lock.json`'s `packages` dict has a `node_modules/<dep>`
key at all. A missing key means a clean `npm ci` will not install it.

**The `npm install` trap — read this before touching a stale lockfile.** The
obvious fix — `cd products/<slug>/frontend && npm install` — is **wrong** for
this class. Without the discipline of `npm ci` (which refuses to touch
anything beyond what the lock already pins), a bare `npm install` **re-resolves
the ENTIRE dependency tree** against the current npm registry — every
`^`-ranged package can bump to a newer minor/patch, producing hundreds of
unrelated version churns (535 measured on one product from doing this
naively). That noise (a) buries the ONE real fix in an unreviewable diff and
(b) risks a real regression from an unrelated version bump nobody asked for.

**The correct fix, in order of preference:**

1. **Scoped install** — `npm install <dep>@<same-range-as-package.json>`
   inside the affected product's `frontend/` — installs (and locks) only the
   named package(s) plus their own transitive closure; does not touch
   unrelated top-level entries. Verify with `git diff --stat` that the
   lockfile diff is small and scoped to the new package(s) before committing.
2. **Surgical splice** (when even a scoped install pulls in registry-version
   drift you don't want, or you're offline) — copy the missing
   `node_modules/<dep>` entries **verbatim** from a sibling product's lockfile
   that already has them resolved (same registry, same version range ⇒
   byte-identical resolution), and mirror the same dep names into the
   target's root manifest entry (`packages[""].dependencies`) if they're
   missing there too. Always validate afterward with a REAL `npm ci` (which
   refuses to touch the lockfile — a clean pass with `diff` showing the
   lockfile byte-identical to what you spliced is your proof) before trusting
   the splice.
3. **Never** run a bare `npm install` across the whole tree to "fix" one
   missing dep — see the trap above.

## Axis 2 — hardcoded product-slug-set literal

**Mechanism.** A literal collection of ≥3 live product slugs — whether a
Python tuple/set/list (`seed/lib/backend/tests/`) or a bash array
(`scripts/infra/*.sh`, e.g. `ALL_SLUGS=(core erp-imobiliario ...)`) — goes
stale the instant the fleet changes: a product added, removed, consolidated,
or (the `knowledge-extractor` shape) scaffolded-but-never-deployed. The two
prior instances (`cors_registry` + `per_product_cors_sentinel`, W3.5) were
Python test fixtures; the `ALL_SLUGS` instance is a build/CI shell script —
same class, a wider blast radius (aborts the whole fleet image build, not
just one test).

**Detection — `check_hardcoded_product_slug_set`** (`compliance.py`, severity
`warning`; extended 2026-07-22 to a second surface). Two scan legs:

1. Python AST walk of `seed/lib/backend/tests/*.py` for a literal
   `Assign`/`AnnAssign` collection containing ≥3 live product slugs.
2. Regex extraction of `NAME=( ... )` bash-array assignments in
   `scripts/infra/*.sh` (bash isn't `ast.parse`-able) — same ≥3-slug
   threshold, same `slug-literal-ok` / `registry-exempt` / `not-a-product-set`
   opt-out convention.

**The root fix — `scripts/infra/build-and-push.sh`.** `ALL_SLUGS` is now
derived at run time from `deploy/fleet/docker-compose.prod.yml`'s
`ghcr.io/jraphaelsst/noctus-<slug>:` image references (the file that actually
defines the deployable fleet) — not a second hand-copied list. A real,
on-disk-but-undeployed product slug (passed in, e.g., by CI's
changed-files-derived build scope) is now **deliberately skipped** with a
logged message rather than aborting the whole build; a genuinely bogus/typo'd
slug (not on disk at all) is still a fatal `exit 2` — the fatal branch is
correct there, it just needed to stop firing on a REAL product.

**Regex-collision gotcha (found authoring this very fix).** The
`check_prod_exposure_consent` keeper (`KB § PATTERNS/devops/prod-exposure-consent.md`)
ALSO regex-scans `scripts/infra/build-and-push.sh` for `ALL_SLUGS=\(([^)]*)\)`
to compute the prod-exposure-surface slug set. An explanatory code comment
that happens to contain the literal text `ALL_SLUGS=(...)` (e.g. "previously
a hand-maintained `ALL_SLUGS=(...)` literal here") gets matched by THAT
regex too — `re.search` finds the comment before the real array — producing a
bogus `'...'` "new arrival" finding that broke the compliance baseline test.
Lesson: when documenting a removed literal pattern in a comment inside a file
another keeper regex-scans, don't reproduce the exact literal shape (write
`ALL_SLUGS` a literal array instead of `ALL_SLUGS=(...)`).

## Gate wiring — local, before it ever leaves the machine

Both axes are gated in `scripts/hooks/pre-commit` (§6d / §6e), **staged-path
scoped** so the cost is paid only when relevant:

- **§6d** (`--check-hardcoded-product-slug-set`) fires when
  `scripts/infra/*.sh`, `seed/lib/backend/tests/*.py`, or `start.sh` is staged.
- **§6e** (`--check-product-lockfile-dep-sync`) fires when a product
  `package.json`/`package-lock.json`, `seed/lib/frontend/package.json`,
  `seed/lib/frontend/src/**/*.ts(x)`, or `seed/framework/frontend/package.json`
  is staged.

Both compose into `check_all_products()` (the CI-side + `noctus.dev.validate`
aggregate) as well — a CI-only gate is not acceptable for this class (that IS
the "discovered only in CI, after promotion" loop being closed); the
pre-commit gate is what stops it from ever reaching a commit in the first
place. CLI: `python mcp/noctusai/cli.py --check-hardcoded-product-slug-set` /
`--check-product-lockfile-dep-sync [--worktree-path <wt>]`.

## Composes with

`KB § PATTERNS/devops/base-image-dep-freshness.md` (the sibling build-artifact
staleness class — base-image `node_modules` vs. declared `package.json`;
that doc's "Lockfile↔package.json sync" section previously forward-referenced
"a `check_frontend_lockfile_sync` keeper" — this is that keeper, now shipped)
· `KB § PATTERNS/devops/prod-exposure-consent.md` (shares the
`scripts/infra/build-and-push.sh` scan surface — see the regex-collision
gotcha above) · `KB § PATTERNS/common/gate-methodology-sync.md` (gate ships
with mechanism, same commit) · `KB § PATTERNS/architect/project-execution.md`
§ DRY recurrence rule (N=3 triggered this doc) · `feedback_hardcoded_product_slug_set_keeper`
(the original Stage-2 memory this axis's Python-AST leg codifies).

## Third axis — the BUILD SET is not the FLEET SET (2026-08-11)

The same "derive, don't hand-maintain" rule, applied to a question the earlier
two axes never asked: *which products should a push actually rebuild?*

`build-and-push.yml` treated any change under `seed/**` as **rebuild the whole
fleet** — correct reasoning (a shared base moved) with a wrong denominator. The
fleet is `docker-compose.prod.yml`: **11** services, of which **7 are
`ativo=false`** in the catalog and are products we have explicitly decided not
to touch (`KB § PATTERNS/architect/product-working-scope.md`). So a one-line
`package.json` edit cost a full 11-product build and put image churn on things
nobody deploys. This landed the same day the fleet moved to PROD-ONLY, where
build minutes and disk are exactly the thing being conserved.

**Two files, two questions — do not conflate them:**

| File | Answers | Consumed by |
|---|---|---|
| `deploy/fleet/docker-compose.prod.yml` | what CAN run on the VPS (the fleet) | `build-and-push.sh` `ALL_SLUGS`, the VPS |
| `deploy/fleet/build-scope.txt` | what we MAINTAIN IMAGES FOR (the active set) | `build-and-push.yml` push-triggered scoping |

An inactive product keeps serving its last-built image until it is reactivated —
nothing is torn down; it just stops being rebuilt.

**Derived, never hand-typed.** The active set is a CATALOG fact
(`ativo = true AND deploy_scope = 'live'`, plus `core`, the platform shell that
deliberately has no `products` row), so `noctus.dev.refresh_build_scope` /
`--refresh-build-scope` generates the file. Hand-editing it recreates precisely
the frozen-slug-literal class the first axis exists to prevent.

**Both silent failure modes are made loud** — this is the whole design:

- *A live product missing from the scope* → its image silently stops being
  built. `refresh_build_scope` **refuses to write** a scope file whose live set
  has no fleet service, naming the offender.
- *A scope slug with no fleet service* → silently never builds while looking
  healthy. The workflow **hard-fails** (`::error::`) and names
  `--refresh-build-scope` as the fix.
- *A changed product dropped for being inactive* → announced via `::notice::`,
  never silently truncated (the no-silent-caps rule).

**Escape hatch:** `workflow_dispatch` ignores the file entirely — pass explicit
`products`, or leave empty for the full fleet. Manual override stays manual.

Pinned by `mcp/noctusai/tests/test_build_scope.py` (20 tests), which also
asserts the workflow text still reads the scope file, still fails loudly, and
still announces drops — the shell lives in YAML, so no other suite executes it.

## Fourth axis — an EXACT `overrides` entry is a fleet-wide FREEZE (2026-08-11)

Same family, opposite direction: the first three axes are about a mirror going
**stale**; this one is about a constraint that can never move **at all**.

**N=3 in a single day** — `postcss "8.5.10"`, `ws "8.20.1"`,
`react-router "6.30.4"`. Every one was added by a *security* cleanup
("resolve Dependabot npm alerts"): **the CVE fix created the freeze.**

Three properties compound, and none is visible at review time:

1. **It wins over everything.** An override forces that version for every
   transitive occurrence, overriding peer ranges and direct deps. npm emits no
   warning about the contradiction — the override simply wins.
2. **It never moves.** An exact value is not a range, so `npm install` (even
   `--package-lock-only`) can never upgrade it.
3. **It is invisible.** It is not in `dependencies`, so a reviewer reading the
   dependency list never sees the constraint that is actually binding.

### The load-bearing insight: the LOCKFILE is already the freeze

CI builds with `npm ci`, which installs `package-lock.json` **exactly**. Nothing
floats at build time regardless of whether the declared value is `^8.5.18` or
`8.5.18`. Proof from the 2026-08-11 unfreeze: converting all 20 exact overrides
to carets produced **zero lockfile change** across 14 manifests.

So an exact override adds **no** reproducibility and removes **all**
upgradeability — a strictly dominated option, not a tradeoff.

### Why the blast radius is always fleet-wide

The seed is the amplifier. One override in `seed/lib` + `seed/framework` is
copied into 12 products + the template: **one pin becomes 14**. This is the
`overrides`-specific corollary of "seed defaults = canonical answer" — an exact
version is never a canonical answer, it is a snapshot of one afternoon.

### How react-router actually failed

`peerDependencies: react-router-dom ^6.0.0` + `overrides: react-router 6.30.4` +
Dependabot pushing `react-router-dom@7`. **Three declaration sites, no coherence
check**, so the PR contradicted the repo and could never go green — which read as
*upstream incompatibility* when it was entirely self-inflicted. The real
migration was package.json-only: the whole API surface across 172 files is 11
symbols, all unchanged in v7, needing **zero** source edits.

### The rule

> **An `overrides` entry MUST be a range. The caret holds the CVE floor and pins
> the major; the lockfile pins the resolution.**

Per-product divergence needs **no new mechanism**: a product that must lag pins
in its **own `dependencies`** — scoped to one product, visible where reviewers
look, and it cannot leak to the other 11. That is the sanctioned escape hatch,
and `check_override_is_range` deliberately does **not** flag it.

Enforced by `check_override_is_range` (severity `high`) — pre-commit when an npm
manifest is staged, plus the `check_all_products()` aggregate. Opt-out for a
genuine freeze: a `pin-ok` / `deliberate-freeze` rationale comment. CLI:
`python mcp/noctusai/cli.py --check-override-is-range`. Pinned by
`mcp/noctusai/tests/test_check_override_is_range.py` (22 tests, both directions —
including that `8.x` is a RANGE, which a naive "starts with a digit" check
misclassifies).

## Fifth axis — a per-product COVERAGE list, not just a slug SET (2026-08-13)

The first four axes are about a value (a lockfile snapshot, a slug literal, a
build-set membership, an override version) drifting stale. This axis is the
same class applied to a **coverage** list — a file that must carry one entry
*per product on disk* — where the drift is an entry going **missing
entirely**, not a stale value inside an existing entry.

**The incident.** `.github/dependabot.yml` listed npm blocks for 9 of 12
product frontends. The three missing — `igig`, `orbity`, and `products/seed`
— are ALL in `deploy/fleet/build-scope.txt` (the live set). `igig` had been in
production since **2026-08-09** with **zero** dependency-update coverage for
four days: no Dependabot alert, no update PR, nothing, because nothing was
watching that directory. Fixed by hand in `a40814b9` (2026-08-13; coverage
12/12 + an 8-entry fleet-major `ignore:` guard added to all 14 npm blocks —
see the Fourth axis above for what that guard is).

**A second live instance, found by looking for siblings** (this doc's own
"generalise if the evidence supports it" discipline, applied while building
the fix). `.github/workflows/test.yml`'s per-product CI `matrix: product:`
lists:

- `product-backend-tests` (pytest): 9 of 12. Missing `igig` (17 test files),
  `orbity` (31), `seed` (6) — every one a product with REAL,
  currently-uncollected backend tests. The job's own comment said "Matrixed
  over ALL 9 products with a backend suite" — true when written (2026-05-31),
  stale the instant 3 more products joined the fleet.
- `product-frontend-tests` (vitest): 8 of 12. Missing `orbity` (real vitest
  spec files under `src/hooks/__tests__/`) — a real gap. `knowledge-extractor`
  / `igig` / `products/seed` are **legitimately** absent: each has a
  `vitest.config.ts` but zero `*.test.ts(x)` files, and `vitest run` hard-fails
  on "no test files found" (the job's own comment states this rule). The
  required-set predicate here is therefore **"has ≥1 qualifying test file"**,
  never "exists on disk" — the coverage axis needs a per-surface predicate,
  not one universal slug set.

Both are the same failure shape as the first four axes:
**a hand-maintained per-product list silently stops tracking the products
that should be in it, discovered only after the gap already cost something**
(missed CVE alerts for dependabot; three products' backend tests and one
product's frontend tests never running in CI, invisible behind a permanently-
green workflow).

### Two surfaces, one class, two mechanisms (not one — and why)

Per `KB § PATTERNS/common/gate-methodology-sync.md`, each surface ships
BOTH a generator (compliance by construction) and a keeper (backstop),
same commit:

| Surface | Generator (MCP tool) | Keeper | Module |
|---|---|---|---|
| `.github/dependabot.yml` | `noctus.dev.refresh_dependabot_coverage` | `check_dependabot_product_coverage` | `dependabot_sync.py` |
| `.github/workflows/test.yml` matrices | `noctus.dev.refresh_ci_matrix_coverage` | `check_ci_test_matrix_coverage` | `ci_matrix_sync.py` |

They are **two mechanisms, not one parameterised engine**, because the two
axes that would need to be shared — the YAML shape (multi-line block with a
guard sub-section vs. a flat `- item` array) and the required-set predicate
(dependabot: "has a `frontend/package.json`", unconditionally; CI matrix:
"has a qualifying test file", which the dependabot surface has no analogue
of) — are genuinely different enough that forcing one function to branch on
both would be less readable than two small, parallel modules. What IS shared
across both, deliberately, is the **contract**:

1. **Targeted repair, never a full-file rewrite.** Both files carry
   load-bearing hand-written rationale comments (why product
   `requirements.txt` files are excluded from Dependabot; why the FE test
   matrix excludes products with no spec files yet). A parser that only
   locates block boundaries + list-item lines by regex, then splices new
   lines in at a computed anchor index (bottom-to-top so earlier anchors
   never shift), leaves every existing byte untouched.
2. **Idempotent.** A second run against an already-fixed file reports
   `in-sync` / `changed: False` and writes nothing.
3. **Report stale, never auto-delete.** A block/entry that no longer
   resolves (deleted product, or — CI-matrix only — a product whose
   qualifying tests were removed) is surfaced in the `stale` field but never
   removed automatically; restoring vs. deleting is a human call.
4. **The required-set predicate is filesystem-derived, not catalog-derived**
   (contrast with the Third axis's `build-scope.txt`, which deliberately IS
   catalog-scoped to `ativo=true`). Both dependabot and CI-matrix coverage
   should include an inactive-but-on-disk product too — a CVE or a broken
   test in a product we're not actively deploying is still worth catching.

### Gate wiring

Both pre-commit-gated (blocking, severity `high`), staged-path scoped, and
composed into `check_all_products()`:

- **`--check-dependabot-product-coverage`** fires when `.github/dependabot.yml`
  OR any `products/*/frontend/package.json` is staged — a **new product** is
  the trigger that matters most, and that's the case where `dependabot.yml`
  itself is NOT staged.
- **`--check-ci-test-matrix-coverage`** fires when `.github/workflows/test.yml`
  OR any `products/*/backend/tests/*.py` OR `products/*/frontend/src/*.test.tsx?`
  is staged — a product's FIRST test file is exactly the commit that should
  add it to the matrix.

Fix commands: `python mcp/noctusai/cli.py --refresh-dependabot-coverage` /
`--refresh-ci-matrix-coverage` (both accept `--dry` to preview). Pinned by
`mcp/noctusai/tests/test_dependabot_sync.py` +
`test_check_dependabot_product_coverage.py` (29 tests) and
`test_ci_matrix_sync.py` + `test_check_ci_test_matrix_coverage.py` (20 tests),
including a reconstruction of the exact pre-fix `igig`/`orbity`/`seed` shape
against synthetic fixtures — proving the detectors would have caught the real
historical bug, not just "the current tree happens to be clean."

### Other per-product lists checked and deliberately left alone

Looked for siblings beyond the two fixed above; none of these needed a new
mechanism:

- **`deploy/fleet/docker-compose.prod.yml`** and **`deploy/tunnel/ingress.yml`**
  — these are the prod-EXPOSURE surfaces. Adding a product to either one IS
  the promotion decision (`KB § PATTERNS/devops/prod-exposure-consent.md`),
  gated by `check_prod_exposure_consent`. Auto-deriving a missing entry here
  would silently promote a product to production — the opposite of what this
  doc's mechanism should do. Left manual, deliberately.
- **`start.sh`'s `PRODUCTS` array`** — this is the upstream **source of
  truth** everything else in this doc derives FROM (`parse_products_registry()`
  reads it), auto-appended by `noctus.dev.scaffold_product`. It is not itself
  a drifting mirror.
- **`.github/workflows/build-and-push.yml`**, **`deploy-prod.yml`**,
  **`seed-typecheck.yml`**, **`embedding-cache-gate.yml`** — no hardcoded
  per-product list; they already derive from `build-scope.txt` or run
  product-agnostically.
- **`KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md`'s product roster** — already
  gated: the pre-commit hook (`CLAUDE.md` § 4) blocks a commit that adds
  `products/<slug>/` without a matching roster row.
