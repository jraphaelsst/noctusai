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
