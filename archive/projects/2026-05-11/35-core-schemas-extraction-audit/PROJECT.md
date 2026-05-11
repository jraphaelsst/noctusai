# core-schemas-extraction-audit — Project Document

> Audit-only project. This document is the OUTPUT of Engineer CORE-SCHEMAS-AUDIT's
> read-only survey of `products/core/backend/app/routers/`. It scopes a follow-up
> extraction-and-migration project ("core-schemas-extraction") that will lift
> inline `BaseModel` classes into `products/core/backend/app/schemas/` and adopt
> `noctusai_lib.api.StrictHttpModel` (Wave-2 carve-out closure).

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Audit complete — ready for architect dispatch of follow-up extraction project
- **Owner / stakeholders:** USER (joaoraphaelsst@gmail.com) · Engineer CORE-SCHEMAS-AUDIT (audit) → architect (dispatch)
- **Related docs:**
  - `KB § PATTERNS/pydantic-strict-http.md` (StrictHttpModel migration recipe)
  - `feedback_pydantic_silent_drop_kills_writes.md` (memory — bug class this closes)
  - `commit 582666f` (`feat(strict-http-wave-2)`) — explicitly carved out core as follow-up
  - `KB § backend/01-CORE.md` (per-product backend spec)
- **Project slug:** `core-schemas-extraction-audit` — lives at `projects/<slug>/` (cross-product follow-up scoping; not yet a single-product project even though only core is touched, because the *outcome* is a separate execution project also rooted at `projects/`). Per `KB § PATTERNS/project-execution.md §1 + §8`.

---

## 1. Context & Purpose

`products/core/` is the only backend without an `app/schemas/` directory. All HTTP-boundary `pydantic.BaseModel` subclasses live inline in 22 of 29 router files (40 classes, 280 LoC). The two consequences:

1. **StrictHttpModel gap (the bug-class).** PF and therapy were migrated to `StrictHttpModel` in commit `582666f` — extra-key requests now 422 instead of silently dropping. Core wasn't migratable in that wave because the migration codemod walks `app/schemas/**`, which core doesn't have. Core endpoints remain susceptible to the silent-drop misroute bug pattern (memory: `feedback_pydantic_silent_drop_kills_writes.md`).
2. **Convention drift.** Every other backend (pf, therapy, mailing, adconnect, media-scheduling, imobi-scheduling, daily-life, erp, youtube-crawler, seed) ships schemas in `app/schemas/<resource>.py`. Core is the lone exception — a structural fork that the recurrence rule (`N≥3 → formalize`) already fired on long ago, silently.

This audit scopes the closure project: extract → place under `app/schemas/<resource>.py` → flip base class to `StrictHttpModel` → wire imports → add the standard 422 regression test (matching pf/therapy wave-2 pattern).

The win: closes the silent-drop bug class for core (the highest-value, highest-traffic backend in the platform), restores cross-product symmetry, removes an explicit carve-out from the Wave-2 commit message.

---

## 2. Confirmed constraints

Pre-existing from architect brief + observations from audit:

- **Read-only audit scope** — this engineer makes NO source edits to `products/core/*`. *(Audit deliverable is data + recommendation, not code change.)*
- **Migration target shape is known** — `noctusai_lib.api.StrictHttpModel` (verified by reading `products/personal-finance/backend/app/schemas/ativos.py`); one file per resource; `from pydantic import Field` retained alongside `from noctusai_lib.api import StrictHttpModel`. *(Recipe at `KB § PATTERNS/pydantic-strict-http.md`.)*
- **No cross-router imports of inline schema classes** — verified: `grep -rln '<ClassName>' app/ tests/` returns only the defining file for every one of the 40 classes. *(Eliminates the EXTRACT-WITH-CARE risk for almost every router.)*
- **Naming collision exists** — `RoleUpdate` is defined in both `roles.py` (catalog: name + permissions) AND `team.py` (membership: role string only). Different shapes. The follow-up project must rename ONE to disambiguate before extraction collides. *(Recommendation: `team.py:RoleUpdate` → `TeamMemberRoleUpdate`. The team.py shape is the membership role-assignment payload, not a catalog edit.)*
- **`response_model=` usage is rare in core** — only `sso.py` declares one (`@router.post("/session", response_model=SSOSessionResponse)`). *(The companion `seed-keeper-check-response-model-vs-migration` keeper has almost nothing to assert against in core; extraction risk does not include response_model rewiring for 21 of 22 routers.)*
- **Seven routers have zero inline schemas** — `admin_llm_usage.py`, `analytics.py`, `audit_digest.py`, `audit_logs.py`, `entitlements.py`, `templates.py`, `usage.py`. *(Out of scope for this project entirely; not just "leave inline" — they have nothing to leave.)*

---

## 3. Design principles

1. **Mirror the pf/therapy migration recipe exactly.** Same import shape (`from noctusai_lib.api import StrictHttpModel` + retained `from pydantic import Field`), same per-product 422 regression test pattern. No invention.
2. **One file per resource.** `auth.py`'s five request schemas land in `app/schemas/auth.py`; `billing.py`'s three land in `app/schemas/billing.py`. Match router filename; no schema-name flattening that obscures origin.
3. **AST-driven extraction (libcst).** Wave-2 already shipped the codemod at `projects/strict-http-wave-2/migrate.py`. Extend it (don't re-write) to handle the extract-and-move case: parse class definitions from router, write to new file with correct imports, delete from router, add import-back line.
4. **Naming-collision rename FIRST, extraction SECOND.** `team.py:RoleUpdate → TeamMemberRoleUpdate` is a separate AST rename that ships before the extraction wave touches `team.py` or `roles.py`. Avoids merge-pain.
5. **Schemas-dir scaffolding alongside Wave 1.** The follow-up project's first chunk creates `app/schemas/__init__.py` and a sentinel test verifying the dir exists. Subsequent waves only have to drop files.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

Run the six-question checklist (`KB § GUIDES/seed-first-design.md § The seed-first checklist`):

1. **Is the contract identical for every product?** YES for the *target shape* — every product already has `app/schemas/`. Core is the outlier. The contract IS the convention; closing the gap restores symmetry. *(No new seed-side abstraction needed — the convention is already platform-wide.)*
2. **Is the data source product-specific?** YES — the schemas are core-specific (auth, billing, SSO, organizations, etc.). They don't belong in seed.
3. **Is the placement product-specific?** YES — `products/core/backend/app/schemas/` is the destination; mirrors `products/personal-finance/backend/app/schemas/`.
4. **Is the visibility / permission rule the same?** N/A — schemas are HTTP-boundary value objects, not gated capabilities.
5. **Does the seam already exist in seed?** YES — `noctusai_lib.api.StrictHttpModel` is the seed-side primitive. Already shipped. Already adopted by pf/therapy. *(No seed-side work in the follow-up project — it consumes the existing primitive.)*
6. **Default-on or opt-in?** DEFAULT-ON for `StrictHttpModel` (every HTTP-boundary class flips); opt-out only with explicit `model_config = ConfigDict(extra="allow")` and a documented rationale in the class docstring (none identified during audit — every core schema looks strict-safe).

**Litmus — per-product code count this design requires:**

- [x] **A small section** — the follow-up project lives entirely inside `products/core/backend/`. New files in `app/schemas/`, edited imports in `app/routers/`, one new test file. No seed-side work, no other-product work. *(Per-product count = 0 outside core; core itself is the per-product subject — this IS the closure of a per-product gap, not the creation of a new replication pattern.)*

**Phase plan implications:** §6 walks through WAVES of routers within ONE product. This is correct — there is no "for each product" framing; the work is core-only because core is the lone outlier. No restart needed.

---

## 4. Scope

**In scope (for the FOLLOW-UP project this audit scopes):**
- Create `products/core/backend/app/schemas/` + `__init__.py`.
- Extract all 40 inline `BaseModel` classes from 22 router files into `app/schemas/<router-basename>.py`.
- Flip every extracted class's base from `BaseModel` to `StrictHttpModel` (matching pf/therapy wave-2).
- Update router files to `from app.schemas.<resource> import X, Y, Z` instead of inline `class X(BaseModel)`.
- Rename `team.py:RoleUpdate` → `TeamMemberRoleUpdate` (naming-collision fix) BEFORE extracting that router's schemas.
- Add `tests/routers/test_strict_http_unknown_field.py` per the wave-2 pattern (one representative Create returns 422; assert detail names the offending field).
- Verify `pytest products/core/backend/` green — current baseline + new 422 test.

**Out of scope (for now — with reason):**
- **The seven empty routers** (`admin_llm_usage`, `analytics`, `audit_digest`, `audit_logs`, `entitlements`, `templates`, `usage`) — *no inline schemas exist; nothing to extract.*
- **`response_model=` adoption across core routers** — *separate concern; tracked by the `seed-keeper-check-response-model-vs-migration` keeper. Core declares `response_model` once (sso.py). Adoption is a downstream project.*
- **Service-layer DTOs and internal `BaseModel`s** — *this audit only enumerated router files; if service-layer `BaseModel`s exist they're not HTTP-boundary and don't need StrictHttpModel. Confirm in Phase 0 of the follow-up.*
- **Frontend type regeneration** — *core frontend reads response JSON, not request schemas; extraction shouldn't shift response shapes. If a wave breaks anything, treat as a separate finding.*

---

## 5. Architecture / Data Model

**Target file layout (post-extraction):**

```
products/core/backend/app/
├── schemas/                             # NEW — currently absent
│   ├── __init__.py
│   ├── admin_cache.py                   # FlushBody
│   ├── admin_llm_spend.py               # BudgetUpdate
│   ├── api_keys.py                      # ApiKeyCreate, ApiKeyUpdate
│   ├── auth.py                          # SignupRequest, LoginRequest, ProfileUpdate, PasswordChange, RefreshRequest
│   ├── billing.py                       # CheckoutRequest, PortalRequest, CancelRequest
│   ├── credentials.py                   # CredentialsBody
│   ├── licenses.py                      # LicenseGrant
│   ├── me_consents.py                   # ConsentToggle
│   ├── oauth.py                         # OAuthCallbackBody
│   ├── onboarding.py                    # StepComplete, CompanyDetailsUpdate
│   ├── organizations.py                 # OrgUpdate
│   ├── plans.py                         # PlanCreate, PlanUpdate
│   ├── products.py                      # ProductCreate, ProductUpdate
│   ├── roles.py                         # RoleCreate, RoleUpdate (catalog)
│   ├── settings.py                      # PlatformSettingBody, OrgSettingBody
│   ├── sso.py                           # SSOTokenRequest, SSOValidateRequest, SSOSessionRequest, SSOSessionResponse
│   ├── subscriptions.py                 # SubscriptionCreate, SubscriptionUpdate
│   ├── team.py                          # InviteCreate, TeamMemberRoleUpdate (renamed), AcceptInviteRequest
│   ├── test_accounts.py                 # TestAccountCreate
│   ├── users.py                         # UserUpdate
│   └── webhooks.py                      # WebhookCreate, WebhookUpdate
└── routers/                             # 22 files lose their inline schemas, gain one import line each
```

**Reference file shape (mirror PF's `app/schemas/ativos.py`):**

```python
from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class ApiKeyCreate(StrictHttpModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: Optional[list[str]] = None
```

---

## 6. Implementation phases

**For the FOLLOW-UP project.** This audit project itself is single-phase (write the audit, file the doc, push the branch).

Each wave below is a candidate dispatch unit. Cumulative LoC moved is small (280 LoC of schemas + 22 import-line additions + 22 deletions) — these waves are sized by *risk*, not by LoC.

### Audit Phase 0 — Survey ✅
- [x] List all `products/core/backend/app/routers/*.py` (29 files; 28 routers + `__init__.py`).
- [x] Verify `app/schemas/` does NOT exist in core (confirmed: `ls app/schemas` → ENOENT).

### Audit Phase 1 — Per-file inventory ✅
- [x] libcst-parse every router; identify `BaseModel`/`StrictHttpModel` subclasses; capture LoC per class.
- [x] Categorize by name-suffix (Create / Update / Out / Filter / In/Request / Body/Payload / Other / List).
- [x] Tally totals: 40 classes; 280 schema-LoC across 22 of 28 routers.

### Audit Phase 2 — Migration scoping ✅
- [x] For each router: count classes, schema-LoC, `response_model=` usage.
- [x] Cross-module reference check (`grep -rln '<ClassName>' app/ tests/`) → no cross-router imports of any schema class. Risk floor.
- [x] Detect naming collisions across routers → ONE found: `RoleUpdate` (roles.py + team.py, different shapes).

### Audit Phase 3 — Per-file recommendation ✅
- [x] Tag each router file: EXTRACT-AND-STRICT / EXTRACT-WITH-CARE / LEAVE-INLINE-ACCEPT.

| Router | Schemas | sLoC | response_model | Recommendation | Notes |
|---|---|---|---|---|---|
| `admin_cache.py` | 1 | 7 | — | EXTRACT-AND-STRICT | Trivial; one body schema. |
| `admin_llm_spend.py` | 1 | 4 | — | EXTRACT-AND-STRICT | Trivial. |
| `api_keys.py` | 2 | 12 | — | EXTRACT-AND-STRICT | Standard Create/Update pair. |
| `auth.py` | 5 | 25 | — | EXTRACT-AND-STRICT | Five small request schemas; highest count but flat. |
| `billing.py` | 3 | 39 | — | EXTRACT-AND-STRICT | Largest schema-LoC (CheckoutRequest=21); review for Field validators. |
| `credentials.py` | 1 | 7 | — | EXTRACT-AND-STRICT | Trivial. |
| `licenses.py` | 1 | 6 | — | EXTRACT-AND-STRICT | Trivial. |
| `me_consents.py` | 1 | 4 | — | EXTRACT-AND-STRICT | Trivial. |
| `oauth.py` | 1 | 5 | — | EXTRACT-AND-STRICT | Trivial. |
| `onboarding.py` | 2 | 12 | — | EXTRACT-AND-STRICT | Standard pair. |
| `organizations.py` | 1 | 6 | — | EXTRACT-AND-STRICT | Trivial. |
| `plans.py` | 2 | 27 | — | EXTRACT-AND-STRICT | Larger Pydantic Field annotations; mechanical. |
| `products.py` | 2 | 20 | — | EXTRACT-AND-STRICT | Standard. |
| `roles.py` | 2 | 15 | — | EXTRACT-AND-STRICT | One half of the naming collision (catalog `RoleUpdate`). KEEPS its name. |
| `settings.py` | 2 | 11 | — | EXTRACT-AND-STRICT | Two body-style schemas. |
| `sso.py` | 4 | 19 | YES | EXTRACT-WITH-CARE | Only router using `response_model=SSOSessionResponse`; verify import path of response_model still resolves after extraction. |
| `subscriptions.py` | 2 | 18 | — | EXTRACT-AND-STRICT | Standard. |
| `team.py` | 3 | 18 | — | EXTRACT-WITH-CARE | NAMING COLLISION — `RoleUpdate` here is membership-role payload; rename to `TeamMemberRoleUpdate` BEFORE this router's extraction. Also imports `invalidate_sso_cache_for_user` from `sso.py` (functions, not schemas — unaffected, but worth knowing). |
| `test_accounts.py` | 1 | 7 | — | EXTRACT-AND-STRICT | Trivial. |
| `users.py` | 1 | 6 | — | EXTRACT-AND-STRICT | Trivial. |
| `webhooks.py` | 2 | 12 | — | EXTRACT-AND-STRICT | Standard pair. |

(Seven empty routers — `admin_llm_usage`, `analytics`, `audit_digest`, `audit_logs`, `entitlements`, `templates`, `usage` — are not listed: zero schemas, no work.)

### Audit Phase 4 — Wave plan ✅

**Wave 1 — Naming-collision rename (pre-extraction, MUST run first).**
- `team.py:RoleUpdate` → `TeamMemberRoleUpdate`. AST rename via libcst. Update the one consumer in `team.py` (the route handler signature). Verify pytest still green. **One small chunk; one engineer; no other work bundled.**

**Wave 2 — Schemas dir scaffolding + lowest-risk batch (EXTRACT-AND-STRICT, no edge cases).** 8 routers, ~50 sLoC total:
- `admin_cache.py`, `admin_llm_spend.py`, `credentials.py`, `licenses.py`, `me_consents.py`, `oauth.py`, `organizations.py`, `users.py`.
- Single class each; trivial extract; mechanical codemod.
- Creates `app/schemas/__init__.py` + 8 resource files. Adds `tests/routers/test_strict_http_unknown_field.py` (one representative — `OrgUpdate` extras → 422).

**Wave 3 — Standard EXTRACT-AND-STRICT batch.** 11 routers, ~190 sLoC total:
- `api_keys.py`, `auth.py`, `billing.py`, `onboarding.py`, `plans.py`, `products.py`, `roles.py`, `settings.py`, `subscriptions.py`, `test_accounts.py`, `webhooks.py`.
- Standard Create/Update + request-body schemas. Mechanical via the wave-2-extended codemod.
- Includes `billing.CheckoutRequest` (21 LoC — largest single schema; double-check Field validators survive base-class swap).
- Includes `roles.RoleUpdate` (catalog — retains its name; safe because team.py was already renamed in Wave 1).

**Wave 4 — EXTRACT-WITH-CARE batch.** 2 routers, ~37 sLoC:
- `sso.py` — verify `response_model=SSOSessionResponse` still resolves (extracted class's import gets added at top of router; no semantic change but worth running pytest end-to-end).
- `team.py` — extract `InviteCreate`, `TeamMemberRoleUpdate` (post-rename), `AcceptInviteRequest`. Verify cross-router function imports (`from app.routers.sso import invalidate_sso_cache_for_user`) still work (they're functions, not schemas — unaffected; sanity-check anyway).

**Wave 5 — Verification & close.**
- Run full `pytest products/core/backend/` (currently ~? passing; need baseline pre-Wave-1).
- Run `noctus.hound.scan` for any drift the waves surfaced.
- Update `commit 582666f`'s carve-out comment retroactively (or note closure in change log).
- Delete this audit project's folder; the `core-schemas-extraction` execution project's PROJECT.md becomes the durable artifact.

**Wave economics:**
- Wave 1 + 2 are dispatchable in parallel only if Wave 1 ships first (Wave 1 must FF-merge before Wave 2 dispatches — see KB §18 wave-based dispatch). Wave 1 is too small to parallelize internally (one rename).
- Wave 3's 11 routers could be split into 2-3 parallel engineers if wall-clock matters. File-disjoint by router → trivially parallel.
- Wave 4 is small; one engineer.

---

## 7. Open questions

1. **Codemod reuse vs rewrite?** — `projects/strict-http-wave-2/migrate.py` ships the BaseModel→StrictHttpModel flip, but doesn't include extract-and-move. Decision: *extend the existing migrate.py* (add an `--extract` mode) vs *write a fresh `extract_inline_schemas.py` next to it*? Needs decision before Wave 2. *Recommendation: separate script — single responsibility; the wave-2 migrate.py is now historic. Author the new tool at `projects/core-schemas-extraction/scripts/extract_inline_schemas.py`.*
2. **`SSOSessionResponse` is a `response_model=` — should it also flip to `StrictHttpModel`?** — `StrictHttpModel` semantics primarily target inputs (extra=forbid on parse). For *responses*, `extra="forbid"` would only fire if the route ever produces unknown keys, which response_model serialization controls. *Recommendation: still flip it for symmetry; FastAPI's `response_model` re-validates outputs and a forbid-extra is harmless for outputs the route fully controls. Confirm in Wave 4 implementation.*
3. **Service-layer `BaseModel` survey** — out-of-scope for this audit, but the follow-up project should grep `products/core/backend/app/services/**/*.py` for `class .*BaseModel` to confirm no service-layer DTOs need attention. *Decided in Phase 0 of the follow-up project.*

---

## 8. Dependencies & blockers

- **`noctusai_lib.api.StrictHttpModel`** — already shipped (consumed by pf + therapy + adconnect + mailing + others). No seed-side work needed.
- **`projects/strict-http-wave-2/migrate.py`** — useful reference for the BaseModel→StrictHttpModel rewrite step; not a hard dependency since the follow-up will likely author a fresh extract-and-move script.
- **No parallel-agent collision** — no other active project touches `products/core/backend/app/routers/`. Verified: `git log origin/main..HEAD` clean on base branch at audit time.

---

## 9. Success criteria

For the FOLLOW-UP project (the actual extraction):

- `products/core/backend/app/schemas/` exists with one file per non-empty router (21 files + `__init__.py`).
- All 40 schema classes inherit `StrictHttpModel` (verified by `grep -rn 'class .*StrictHttpModel' app/schemas/ | wc -l → 40`).
- No router file contains an inline `class X(BaseModel)` for an HTTP-boundary schema (verified by `grep -rn 'class .*BaseModel' app/routers/ → empty` — except for in-route docstrings or comments).
- `pytest products/core/backend/` green; +1 new test in `tests/routers/test_strict_http_unknown_field.py` asserting 422 on extra-key request.
- `team.py:RoleUpdate` rename done with zero functional change (route still accepts the same JSON).
- No regression in any other product (only core was touched).

For THIS audit project: PROJECT.md filed; branch pushed; report returned to architect with the wave plan. *(Met by current commit.)*

---

## 10. How to use this plan

This is an audit-only PROJECT.md. The execution work happens in a separate project `core-schemas-extraction` (the architect dispatches that one based on this audit's wave plan). Treat this file as a frozen reference once the follow-up project is filed — don't modify it during execution; modifications go in the new project's PROJECT.md change log.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Audit drafted from architect brief (STRICT-HTTP-WAVE-2 carve-out closure). 29 routers surveyed, 40 inline schemas inventoried via libcst, 5 waves proposed (1 rename + 3 extraction + 1 verify). RoleUpdate naming collision flagged. | Engineer CORE-SCHEMAS-AUDIT (Claude Opus 4.7) |
