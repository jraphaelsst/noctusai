# Seed Organ Canonical Set — Phase 1

> Project: `seed-organs-cache` W4 · Registered: 2026-05-29.
> Depth: `KB § PATTERNS/architect/component-bundle-tool.md` · `KB § PATTERNS/architect/component-list-and-validation.md`.

## What an "organ" is

An organ = a validated, reusable, embedded, query-able seed component. It ships a sidecar `<Name>.organ.yaml` next to its source with 8 knowledge fields (per the build-learn-cache mindset codified in PROJECT.md §3a of `seed-organs-cache`). It is embedded into `code-embeddings.sqlite` with `chunk_kind='organ'` so it is findable by INTENT via `noctus.dev.find_reusable_component`.

Validation criterion: `validated = consumers ≥ 3 ∧ has_test ∧ no NOC-REMEDIATE markers ∧ no recent bug-fix commits in 14 days`. Derived, never manually asserted.

## Phase-1 canonical set (5 organs, `validation_status=validated`)

| Name | Path | Consumers | Has test | Status | Note |
|---|---|---|---|---|---|
| LoginForm | `seed/lib/frontend/src/design-system/components/LoginForm.tsx` | 9 | no | validated | Auth trio entry point; dual-mode (Supabase + session) |
| ForgotPasswordPage | `seed/lib/frontend/src/design-system/components/ForgotPasswordPage.tsx` | 8 | no | validated | Auth trio; 4-state machine; renderLink render-prop |
| AcceptInvitePage | `seed/lib/frontend/src/design-system/components/AcceptInvitePage.tsx` | 8 | no | validated | Auth trio; fetch-based (no Supabase dep); 5-state machine |
| ResourceManager | `seed/lib/frontend/src/components/ResourceManager.tsx` | 3 | yes | validated | Canonical page-scoped CRUD; self-contained; DRY formalization of N=3 recurrence |
| DigestCard | `seed/lib/frontend/src/design-system/ai/DigestCard.tsx` | 3 | no | validated | AI digest surface; non-destructive error handling; AIFeedbackButtons integration |

**Auth trio**: LoginForm + ForgotPasswordPage + AcceptInvitePage are a single semantic unit — every product that needs direct auth mounts all three. They share the same brandIcon/brandTitle branding seam and zero external deps beyond React.

**ResourceManager** is the exemplar: it is the organ registered first in W3 tests because it has a colocated test file AND is the direct result of applying the DRY N=3 recurrence rule.

## Phase-1 shelfware set (4 items, `validation_status=shelfware`)

These are built but have 0 consumers. Surface explicitly — the anti-pattern is treating 0-consumer components as "available but unused." Shelfware MUST be named.

| Name | Path | Note |
|---|---|---|
| PageSkeleton | `seed/lib/frontend/src/design-system/components/PageSkeleton.tsx` | 0 consumers; built but not wired to any product page |
| LLMSpendBadge | `seed/lib/frontend/src/design-system/ai/LLMSpendBadge.tsx` | 0 consumers; monitoring badge component |
| FakeModeBadge | `seed/lib/frontend/src/components/FakeModeBadge.tsx` | 0 consumers; has test (FakeModeBadge.test.tsx) |
| ErrorBoundary | `seed/lib/frontend/src/components/ErrorBoundary.tsx` | 0 consumers; React error boundary |

Shelfware resolution options: (a) wire to a real consumer → consumers_count rises → `emerging` or `validated`; (b) remove if no planned consumer; (c) accept with `NOC-REMEDIATE[shelfware]` marker + rationale. Do NOT let shelfware age silently.

## Organ sidecar format (8 knowledge fields — per PROJECT.md §3a)

Each organ ships `<Name>.organ.yaml` next to its source:

```yaml
name: ComponentName
path: repo/relative/path/to/ComponentName.tsx
phase: pilot-seed        # pilot-seed | product-phase-2 | etc.
registered_at: "2026-05-29"
validation_status: validated  # derived; may be overridden by keeper

known_facts:             # what we discovered — behaviors, invariants, constraints
  - "..."
errors_encountered:      # bugs hit during dev + resolution + patch SHA
  - "..."
drifts_surfaced:         # pre-existing drift surfaced by this organ's work
  - "..."
alternatives_considered: # designs tried and abandoned + why
  - "..."
manual_validation_log:   # user-provided feedback [{date, validator, finding, status}]
  - {}
integration_test_status: unknown  # or pass/fail + test names
e2e_test:
  path: null             # W5 populates
  status: pending
  last_run: null
  runs_in_ci: false
bugs_fixed_during_dev:   # commit SHAs of in-flight fixes
  - "..."
```

## MCP tools (W4 ships)

| Tool | Purpose |
|---|---|
| `noctus.dev.find_reusable_component` | Query by intent → top-K organ matches (embedding + fallback) |
| `noctus.dev.register_organ` | Embed one organ into code-embeddings cache; idempotent |
| `noctus.dev.register_all_canonical_organs` | Register all 5 Phase-1 organs; idempotent |

CLI: `--find-reusable-component <query> [--top-k N] [--filter-status validated]`
     `--register-organ <name>`
     `--register-all-canonical-organs`

## Phase-2 (next project — social-wiring pilot)

First product organs to register: multi-account integrations CRUD page + settings page from `social-wiring`. Pattern: build → validate → register → query. The loop proven here transfers directly.

## Composes with

- `KB § PATTERNS/architect/component-bundle-tool.md` — the bundle shape `find_reusable_component` enriches with
- `KB § PATTERNS/architect/component-list-and-validation.md` — the `list_components` call that provides validation_status + consumers_count
- `KB § PATTERNS/common/code-embeddings.md` — the cache being extended with chunk_kind='organ'
- `KB § PATTERNS/common/persistent-files-absorption.md` — absorption mindset extended to per-organ continuous knowledge
