# Products Consume Canonical Cached Organs

> **Stage:** s3 — KB codified (same-commit compression; s1+s2 evidence below).
> **Provenance:** s1 from architect Phase 2 scout (seed-organs-cache project, 2026-05-29). s2 in MEMORY.md (`feedback_products_consume_canonical_organs.md`). N≥3 canonical organs already 95%+ consumed on disk — formalizing the gain.
> **Composes with:** `seed-canonical-defaults.md` · `seed-organ-canonical-set.md` · `cache-as-agent-tool.md` · `build-learn-cache-mindset.md`

---

## Rule (load-bearing)

Any organ-shaped component living at `products/<slug>/frontend/src/` MUST import from `@noctusai/lib/...` (the canonical seed location) rather than re-implementing the component locally.

**Named-seam extensions are allowed when DECLARED.** If a product needs product-specific behaviour on top of a canonical organ, it may wrap it — but the wrapper file MUST carry the declaration header:

```tsx
// @consumes-organ DigestCard@1.0 +seam=data-binding
```

Without that declaration, a local function/const that re-declares a canonical organ name is a **blocking violation** (`check_canonical_organ_consumption`, severity `high`).

---

## Design decisions (four decisions baked in, architect Phase 2 accepted by user 2026-05-29)

| Decision | Accepted form |
|---|---|
| **Strictness** | Hard rule. Named-seam extensions allowed when DECLARED in consumer file header (`// @consumes-organ <Name>@<version> +seam=<kind>`). |
| **Evolution** | Additive back-compat seam in seed by default. Full PR + migration guide only on contract break. |
| **Versioning** | `organ_version: MAJOR.MINOR` in each `<organ>.organ.yaml` sidecar (semver-lite). Consumer pin OPTIONAL today — introduced as a best-practice, not a gate. |
| **Consumer registration syntax** | `// @consumes-organ <Name>@<version>` header comment in product-side consumer files. Optional today, keeper-gated in a future s4 pass. |

---

## Canonical organ roster (Phase 1 seed set)

Sourced from `seed/lib/frontend/src/**/*.organ.yaml` and the canonical set table in `KB § PATTERNS/architect/seed-organ-canonical-set.md`. The keeper scans both.

| Organ name | Seed path | Validation status |
|---|---|---|
| `LoginForm` | `seed/lib/frontend/src/components/auth/LoginForm` | validated |
| `ForgotPasswordPage` | `seed/lib/frontend/src/pages/auth/ForgotPasswordPage` | validated |
| `AcceptInvitePage` | `seed/lib/frontend/src/pages/auth/AcceptInvitePage` | validated |
| `ResourceManager` | `seed/lib/frontend/src/components/resource/ResourceManager` | validated |
| `DigestCard` | `seed/lib/frontend/src/components/digest/DigestCard` | validated |

> **Shelfware exclusion:** organs with `validation_status: shelfware` (e.g., `PageSkeleton`, `LLMSpendBadge`, `FakeModeBadge`, `ErrorBoundary` — not yet consumed by any product) are NOT in scope for this keeper. Local re-implementations of shelfware names are ALLOWED until the organ is promoted to `emerging` or `validated`.

---

## Anti-patterns (four known failure modes)

1. **Silent re-fork.** Copy-pasting `LoginForm` into `products/erp/frontend/src/components/LoginForm.tsx` without the declaration header. The user gets two out-of-sync implementations — the canonical one fixes a bug; the fork doesn't.

2. **"Just this once" override.** "I need a small difference, easier to inline." This is the slip that restarts the replication cycle (N=2→triage, N=3→must formalize). Use the named-seam extension instead.

3. **Import-then-wrap-divergent.** Importing the canonical organ but immediately recreating its internals via the wrapper (adding props, changing the data model). If the wrapper is not declared, it bypasses the intent of the pattern; even if declared, excessive seam depth is a sign the organ's contract needs extension at the seed level.

4. **Same-shape rename.** Naming a local component `AuthForm` when it is functionally `LoginForm`. The keeper detects by canonical organ NAME — a same-shape rename evades name-only detection. Known limitation; surface in `scoped-improvement:` when found. The right fix is to import `LoginForm` and alias it locally.

---

## Worked example — the Phase 2 audit finding

When the architect Phase 2 scout ran on 2026-05-29, the platform was already **95% canonical-consumed** on the Phase 1 organ set:

- 12 organ usages across products: all importing from `@noctusai/lib/...` — ALLOWED.
- 1 orphan: `products/erp/frontend/src/components/LoginForm.tsx` — a local re-declaration without the declaration header. BLOCKING (until W2.2 removes it).
- 0 products using the declared-named-seam path (the path is new; future consumers adopt it).

The rule codifies the EXISTING discipline — the 95% is the gain we are locking.

---

## Keeper

`check_canonical_organ_consumption` in `mcp/noctusai/tools/noctus/dev/compliance.py`.

- Severity: `high` (blocking).
- Scan inputs: canonical organ roster from `seed-organ-canonical-set.md` table + `seed/lib/frontend/src/**/*.organ.yaml` (any `validation_status: validated|emerging|canonical`).
- Per organ name: scans `products/*/frontend/src/**/*.{tsx,ts}` for `function <Name>` / `const <Name> =` / `export function <Name>` declarations.
- Per match: checks for `// @consumes-organ <Name>` AND `+seam=` in the same file → ALLOWED. Without declaration → BLOCKING.
- Reports: file:line + the canonical organ's seed path + suggested replacement import.

---

## Composes with

- `KB § PATTERNS/architect/seed-canonical-defaults.md` — the general "seed defaults = canonical answer" principle.
- `KB § PATTERNS/architect/seed-organ-canonical-set.md` — the authoritative canonical roster and validation status derivation.
- `KB § PATTERNS/common/cache-as-agent-tool.md` — use `noctus.dev.find_reusable_component` BEFORE building any FE component (the query side of this rule).
- `KB § PATTERNS/common/build-learn-cache-mindset.md` — each canonical organ accumulates knowledge continuously; consumers inherit the learning.
