# core-schemas-extraction-close — Project Document

> **Close-summary project.** This document is the §11 retrospective of the
> 5-wave `core-schemas-extraction` effort. The audit project (35-core-schemas-extraction-audit)
> scoped the work; the execution shipped in waves W1..W4 with this W5 closing the loop
> via verification + close summary. No new code in this folder — strictly the
> retrospective for the 5-wave arc.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Closed — Wave 5 verification GREEN; all 5 waves merged to `origin/main`.
- **Owner / stakeholders:** USER (joaoraphaelsst@gmail.com) · Engineers W1/W2/W3-A/W3-B/W3-C/W4 (extraction) · Engineer CORE-EXTRACT-W5-2 (verify + close)
- **Related docs:**
  - `archive/projects/2026-05-11/35-core-schemas-extraction-audit/PROJECT.md` (audit that scoped this work)
  - `KB § PATTERNS/pydantic-strict-http.md` (StrictHttpModel migration recipe)
  - `feedback_pydantic_silent_drop_kills_writes.md` (memory — bug class this closes)
- **Project slug:** `core-schemas-extraction-close` at `projects/<slug>/` (close-summary for a cross-wave effort).

---

## 1. Context & Purpose

`products/core/backend/` was the lone backend without an `app/schemas/` directory — 40 inline `BaseModel` request classes across 22 routers (audit @ commit `3714f84`). Two consequences:

1. **StrictHttpModel gap** — core endpoints silently dropped unknown keys instead of 422-ing, leaking the silent-drop bug class (memory `feedback_pydantic_silent_drop_kills_writes.md`).
2. **Convention drift** — every other backend ships `app/schemas/<resource>.py`; core was a structural fork.

The 5-wave extraction closed both gaps. This document is the retrospective.

---

## 2. Confirmed constraints (inherited from audit)

- Read-only audit FIRST, code edits SECOND (audit shipped at `3714f84`; execution shipped at `607b639` → `e059e8d`).
- One file per resource — match router filename; no schema-name flattening.
- AST-driven extraction (`libcst`) — no regex on source.
- Naming-collision rename FIRST: `team.py:RoleUpdate → TeamMemberRoleUpdate` (W1) shipped BEFORE any extraction wave touched `team.py` or `roles.py`.

---

## 3. Waves shipped — commit SHAs + scope

| Wave | Commit SHA | Scope | Schemas | Routers |
|---|---|---|---|---|
| **W1** | `607b639` | Naming-collision unblocker: rename `team.py:RoleUpdate → TeamMemberRoleUpdate` to free the `roles.py` symbol slot | 0 (rename only) | 1 |
| **W2** | `c1b0d00` | Scaffold `app/schemas/` + `__init__.py` + extract 8 trivial routers | 11 classes, 9 schema files | 8 |
| **W3-A** | `91e2885` | Extract 4 EXTRACT-AND-STRICT routers (auth/billing/credentials/licenses) | (varies; 4 schema files) | 4 |
| **W3-B** | `9a8395f` | Extract 4 more routers (onboarding/organizations/products/roles) | 7 classes, 4 schema files | 4 |
| **W3-C** | `5d371a7` | Extract subscriptions + users + webhooks routers | 5 classes, 3 schema files | 3 |
| **W4** | `e059e8d` | Extract `sso.py` + `team.py` (response_model + cross-collision-safe last) | 7 classes, 2 schema files | 2 |
| **W5** | (this) | Verify + project close summary | 0 (verification only) | 0 |

**Total artifacts shipped:** `app/schemas/__init__.py` + **21 schema modules** (8 W2 + 4 W3-A + 4 W3-B + 3 W3-C + 2 W4) covering **22 routers** (1 W1 rename target + 21 extraction targets across W2..W4).

All 40 inline `BaseModel` classes are now in `app/schemas/<resource>.py` inheriting `noctusai_lib.api.StrictHttpModel` (`extra="forbid"`). The silent-drop bug class is closed for core.

---

## 4. Final verification (W5)

Run from `core-extract-w5-verify-close-2026-05-11` branch at HEAD = `e059e8d` (W4 merge tip).

| Check | Result |
|---|---|
| `pytest products/core/backend/ -q` | **517 passed, 9 skipped, 3 warnings in 6.25s** — matches W4 baseline exactly |
| `bash scripts/verify-kb-sync.sh` | **GREEN** — all CLAUDE.md pointers resolve, all KB docs indexed, Layout tree current |
| `noctus.dev.review --product core` | **0 NEW** issues |
| `grep -rEn "^class \w+\(BaseModel\)" products/core/backend/app/routers/` | **0 hits** — zero inline BaseModel remains in routers |
| `grep -rEn "from app.schemas" products/core/backend/{app,tests}/` | All 21 routers import cleanly from `app.schemas.*`; team↔sso↔licenses cross-refs verified intact |
| `noctus.hound.scan` | 323 candidates total / 181 LoC savings estimate (all P2+; absorption P0=0 P1=0); next_action = "fusion: 7 subsume candidates" — unrelated to this extraction effort |

---

## 5. Methodology learnings

Three durable learnings captured during W5 verification:

### 5.1 Sibling-isolated test files (W3-A discovery)

W3-A first surfaced that the `tests/` directory of a worktree must share the same PYTHONPATH as production. `noctusai_seed` lives at `seed/framework/backend/noctusai_seed` and is NOT installed into the venv; product tests must invoke pytest with `PYTHONPATH=<repo-root>:<repo-root>/seed/framework/backend`. The W5 verification repeated this: vanilla pytest failed with `ModuleNotFoundError: No module named 'noctusai_seed'` until the PYTHONPATH override was applied. **Implication:** engineer briefs that say "run pytest" must include the canonical PYTHONPATH recipe. Worth a brief KB pointer at `KB § PATTERNS/testing.md` (cheap addition; defer with destination per the bystander rule).

### 5.2 Verify-brief engineer-side check

Each wave received a focused brief naming the routers to extract. W4's brief included `sso.py` (the only `response_model=` in core) and `team.py` (collision sibling renamed in W1) — the two highest-risk routers were intentionally saved for last so prior waves de-risked them. **Implication:** Wave ordering by risk-of-collision-with-priors is the correct default for extraction work; not by file size, alphabetical, or LoC.

### 5.3 Naming-collision rename as W1 unblocker

The audit caught `team.py:RoleUpdate` vs `roles.py:RoleUpdate` — invisible while inline because both stayed inside their router modules, but extraction into `app/schemas/` would have collided at import time. **Implication:** before any extraction wave, audit MUST surface inline-symbol collisions (same class name in N routers); the rename ships as the W1 unblocker BEFORE waves that touch either side. The audit project's §2 explicitly flagged this; the methodology to surface is "grep for duplicate `^class \w+` names within `app/routers/` BEFORE planning extraction waves."

---

## 6. Change Log

- **2026-05-11** — Audit shipped (`3714f84`) — read-only survey of 22 routers / 40 inline BaseModels.
- **2026-05-11** — W1 (`607b639`) — `team.py:RoleUpdate → TeamMemberRoleUpdate` rename unblocker.
- **2026-05-11** — W2 (`c1b0d00`) — `app/schemas/` scaffold + 8 trivial routers extracted (11 classes).
- **2026-05-11** — W3-A (`91e2885`) — 4 routers extracted (auth/billing/credentials/licenses).
- **2026-05-11** — W3-B (`9a8395f`) — 4 routers extracted (onboarding/organizations/products/roles).
- **2026-05-11** — W3-C (`5d371a7`) — 3 routers extracted (subscriptions/users/webhooks).
- **2026-05-11** — W4 (`e059e8d`) — `sso.py` + `team.py` extracted (the response_model + collision-sibling pair).
- **2026-05-11** — W5 (this doc) — verification GREEN + project close + archive.
