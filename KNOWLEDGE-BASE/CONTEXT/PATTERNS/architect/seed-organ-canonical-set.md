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

## Phase 2 — emerging organs formalized 2026-05-29

Architect scout surfaced 15 organs already canonical in practice. All ship `organ.yaml` + 8 knowledge fields + `organ_version: 1.0`. None have colocated tests → all are `emerging`. Derived via: consumers ≥ 3 ∧ has_test ∧ no NOC-REMEDIATE required for `canonical`.

**Note on path corrections vs. brief:** ScorePill, RankBadge, ProgressRing are in `design-system/gamification/` (not `design-system/ai/` as initially listed). InactivityWarning is at `design-system/InactivityWarning.tsx` (root, not `components/`).

### Components (kind: component, implicit)

| Name | Path | Consumers | Status | Note |
|---|---|---|---|---|
| AppShell | `seed/lib/frontend/src/design-system/components/AppShell.tsx` | 5+ (1 direct + N via createProductLayout) | emerging | Layout wrapper; responsive sidebar; shell trio entry point |
| Sidebar | `seed/lib/frontend/src/design-system/components/Sidebar.tsx` | 5+ (1 direct + N via createProductLayout) | emerging | Prop-driven collapsible nav; brandHref SSO seam |
| Header | `seed/lib/frontend/src/design-system/components/Header.tsx` | 5 direct + N via createProductLayout | emerging | logoutBehavior seam; actions slot; variant prop |
| ScorePill | `seed/lib/frontend/src/design-system/gamification/ScorePill.tsx` | 3 | emerging | Threshold-based color pill; null-safe; sibling to ProgressRing |
| RankBadge | `seed/lib/frontend/src/design-system/gamification/RankBadge.tsx` | 2 | emerging | Gold/silver/bronze/neutral tier badge; gamification convention |
| NotificationBell | `seed/lib/frontend/src/design-system/components/NotificationBell.tsx` | 3 | emerging | Hook-injection pattern; no shadcn dep; standardized Notificacao type |
| LLMProviderSelector | `seed/lib/frontend/src/design-system/components/LLMProviderSelector.tsx` | 2 | emerging | Provider+model picker; stub/unconfigured labeling; presentational |
| ProgressRing | `seed/lib/frontend/src/design-system/gamification/ProgressRing.tsx` | 2 | emerging | Circular SVG progress; over-100 clamped; color tiers match ScorePill |
| AIBadgeStack | `seed/lib/frontend/src/design-system/ai/AIBadgeStack.tsx` | 1 direct + N via layout aiBadge slot | emerging | Badge composer; collapse-when-empty; layout aiBadge default |
| AIFeedbackButtons | `seed/lib/frontend/src/design-system/ai/AIFeedbackButtons.tsx` | 1 direct + indirect via DigestCard+AIIndicator | emerging | Thumbs-up/down; UNIQUE(user_id, output_ref) idempotency; X3 cross-cutting |
| AIIndicator | `seed/lib/frontend/src/design-system/ai/AIIndicator.tsx` | 3 | emerging | ai_outputs router surface; auto-hide; composites ScorePill+AIFeedbackButtons |
| InactivityWarning | `seed/lib/frontend/src/design-system/InactivityWarning.tsx` | 2 | emerging | Session-expiry countdown modal; mirrors useActivityRefresh event model |

### Hooks (kind: hook)

| Name | Path | Consumers | Status | Note |
|---|---|---|---|---|
| useActivityRefresh | `seed/lib/frontend/src/design-system/useActivityRefresh.ts` | 4 (2 barrel + 2 direct path) | emerging | Two-tier activity; multi-tab localStorage; failure backoff |
| useTheme | `seed/lib/frontend/src/design-system/useTheme.ts` | 5 | emerging | localStorage+DOM sync; initialTheme DB-override; onPersist callback |

### Helpers (kind: helper)

| Name | Path | Consumers | Status | Note |
|---|---|---|---|---|
| splitProseIntoParagraphs | `seed/lib/frontend/src/design-system/ai/DigestCard.tsx` | 3 | emerging | Co-located in DigestCard; null-safe; exported via ai/index.ts barrel |

### Path drift surfaced

- `InactivityWarning.tsx` at design-system root (not components/) — `NOC-REMEDIATE[path-cleanup]` logged in sidecar.
- `splitProseIntoParagraphs` co-located in DigestCard.tsx — acceptable at N=3; should move to standalone file if consumers outside ai/ namespace emerge.

## Composes with

- `KB § PATTERNS/architect/component-bundle-tool.md` — the bundle shape `find_reusable_component` enriches with
- `KB § PATTERNS/architect/component-list-and-validation.md` — the `list_components` call that provides validation_status + consumers_count
- `KB § PATTERNS/common/code-embeddings.md` — the cache being extended with chunk_kind='organ'
- `KB § PATTERNS/common/persistent-files-absorption.md` — absorption mindset extended to per-organ continuous knowledge
