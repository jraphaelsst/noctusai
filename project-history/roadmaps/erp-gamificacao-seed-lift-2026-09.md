# erp-gamificacao-seed-lift — re-point erp onto `domain/engagement/` (2026-09)

> Durable record (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Lives here because this is a deliberately DEFERRED, multi-session
> re-point — not this slice's scope, and `projects/<slug>/` is
> ephemeral (archived on close; the deferral would be lost).
> On close: absorb lessons → KB/memory, optionally move to closed/.

## Goal

`products/erp-imobiliario/backend/app/services/gamificacao_service.py`
re-points its point rules + badge conditions + leaderboard onto
`noctusai_lib.domain.engagement` (shipped 2026-09-16 for
`products/community`, wave-0 Slice E), so ERP's hardcoded
`PONTOS_POR_ACAO` dict + lambda badge conditions become data-driven —
matching `KB § CONTEXT/07-GAMIFICATION.md § 8` ("Owner-tunable. ... No
hardcoded business logic.") — and the platform has ONE engagement-scoring
implementation, not two.

## Why deferred (not done in the same slice)

`domain/engagement/` was built for `products/community` only. Re-pointing
ERP in the same slice would make community + erp N=2 simultaneously,
which the wave-0 design explicitly calls "triage, not a forced
extraction": the rule schema (caps semantics, badge-threshold shape,
leaderboard/period reuse) has not yet been validated by a second real
consumer. Re-pointing ERP now risks discovering a schema mismatch after
BOTH consumers already depend on it. See the
`NOC-REMEDIATE[seed-lift]` marker in `gamificacao_service.py`.

## Slices

| # | Title | Files-to-modify | Agent | Status | Wave | Verify recipe | SHA |
|---|---|---|---|---|---|---|---|
| 1 | Community consumes `domain/engagement/` in production, points-rule schema validated against a real product | `products/community/backend/...` | (community build, not this roadmap) | pending | — | community's own points award flow exercises `evaluate`/`PointsLedger` end-to-end | — |
| 2 | Re-point ERP: replace `PONTOS_POR_ACAO`/`BADGES`/lambda conditions with `PointRule`/`BadgeRule` rows + `evaluate`/`evaluate_badges`/`leaderboard` calls; ship ERP's own `PointsLedger` migration (schema=erp's own) | `products/erp-imobiliario/backend/app/services/gamificacao_service.py` + callers + a new migration | backend-engineer | pending | — | `pytest products/erp-imobiliario/backend/tests -k gamificacao` green; erp's existing gamification routes return identical point totals for a fixed fixture set (before/after diff) | — |
| 3 | Delete the `NOC-REMEDIATE[seed-lift]` marker once Slice 2 lands | `gamificacao_service.py` | backend-engineer | pending | — | `grep -c "NOC-REMEDIATE\[seed-lift\]" gamificacao_service.py` == 0 | — |

Status ∈ {pending, in-flight, blocked, shipped, abandoned}.

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-09-16 | Build `domain/engagement/` for community only; defer ERP re-point | Community would make it N=2 immediately, but the design explicitly flags the rule schema as unvalidated by a real second consumer yet — triage, not a forced extraction (`KB § PATTERNS/architect/project-execution.md` recurrence rule: N=2 is triage, not MUST-formalize). |

## Open questions

1. Does ERP's `daily_cap`/`period_cap` need a THIRD cap shape
   `domain/engagement.PointRule` doesn't have (e.g. a per-badge-event
   cap, or a cross-action combined cap for "meta_cumprida")? Only
   surfaces once ERP's real rule rows are mapped onto `PointRule`.
2. ERP's leaderboard is scoped by team/hierarchy (KB § 07-GAMIFICATION.md
   § "Privacy-aware" / "Role-aware") — `domain/engagement.leaderboard`
   ranks a flat `totals` mapping; the role/team scoping stays a
   product-side filter applied to `totals` BEFORE calling `leaderboard`
   (no seed change anticipated, but confirm at re-point time).

## Retrospective (filled at close)

_(pending — fill when Slice 3 lands)_

## Composes with

`KB § CONTEXT/07-GAMIFICATION.md` (owner-tunable rules mandate) ·
`KB § CONTEXT/04-SHARED-LIBRARY.md` (`domain/engagement/` entry) ·
`KB § PATTERNS/common/remediation-markers.md` (the `NOC-REMEDIATE[seed-lift]`
marker this roadmap is the named destination for) ·
`KB § PATTERNS/architect/project-execution.md` (N=2 triage / N=3 MUST-formalize).
