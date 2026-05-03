# NEXT-STEPS — Implementation batch plan

> **Snapshot 2026-05-03.** Action layer for the next implementation waves.
> Background — full project status table lives at `projects/README.md`.
> Deferral details — `KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md`.
> This document is a transient roadmap; refresh after each wave closes.

---

## Priority breakdown

### P0 — Finish-line items (close-paperwork, low-risk)

> ✅ **All P0 finish-line items complete (2026-05-03).**
> - PF org-scoping Phase 8 shipped in `772df8b` (project folder deleted, KB synced, baselines green).
> - 4 closed root project folders deleted (`methodology-extraction`, `llm-tool-call-audit`, `mcp-server-expansion`, `vista-api-mcp`); `mcp/vista/` + `mcp/noctusai/tools/cost_evaluation.py` references repointed to KB / git history. Carry-forward work tracked in `mcp-server-fastmcp-switch` + `whatsapp-seed-absorption` Phase 5.

### P1 — Active in-flight (next concrete step is well-defined)

| Item | Next step | Blocker |
|---|---|---|
| **`absorbed-projects-batch` Tier 1.c** | Execute `scheduling-engine-seed` Phase 0 audit | none |
| **`absorbed-projects-batch` Tier 1.d** | Execute `whatsapp-seed-absorption` Phase 0 audit | none |
| **`erp-schema-drift-deep-audit` Phase 2** | 11-table audit (ERP-side schema reconciliation) | user §7 sign-off on org-scoping model |
| **`repo-state-consolidation`** | Resume Phases 1-3 — re-run per-commit pre-flight gates | user re-engages |
| **`main-core-migrations-batch`** | Tier 1 staleness audit on `repo-state-consolidation` then Tier 1 phase work | upstream Tier 1 |

### P2 — Top deferrals to escalate (from accept-with-rationale catalog — 15 active entries)

1. **`send_message` collision at N=2** → file `send_message-consolidation` follow-up project NOW. Recurrence rule: third product hitting it forces a hasty choice.
2. **`MockSupabaseClient(validate_schema=False)` opt-outs** → flip per-product as each schema-reconciliation project closes (ERP first, therapy second).
3. **Outbound webhook signer in `core/services`** at N=2 → re-evaluate when second outbound subscription product lands.
4. **MCP settings shim local `get_settings()`** → formalize when N=2 non-product process needs the singleton (likely soon — vista MCP just shipped its own).
5. **Digest wrappers at N=4** → instrument a watch for N=5; pre-document boilerplate prefixes while pattern is fresh.

### P3 — Phase-0-ready (scaffolded, awaits focused-session pickup)

- `scheduling-engine-seed` — Phase 0 ready (scheduler primitive absorption)
- `whatsapp-seed-absorption` — Phase 0 ready (WhatsApp framework absorption + idempotency-keys)
- `imobi-scheduling-bot-creation` — downstream of the two above
- `session-review-baseline` — filed-only per user directive; awaits explicit reactivation
- `mcp-server-fastmcp-switch` — Phase 0 ready (FastMCP runtime swap-out)
- `mcp-tool-name-deprecation` — blocked on `mcp-server-fastmcp-switch` Phase 5
- `therapy-platform-wiring` — Phase 0 (api-call inventory) is the gate for Phases 1-9

### P4 — Concept-stage / interrogation pending

- `project-history-ledger` — §7 user interrogation pending
- `adconnect-migration` — descriptive only; no PROJECT.md phase structure yet

### P5 — Future-direction / deferred (no execution scheduled)

`agno-dev-team-future-direction` · `dev-observability-bot-future-direction` · `user-context-bot-future-direction` · `strict-mode-migration` (gated on v2.4)

---

## Recommended sequencing

**Wave 1 — Close PF org-scoping** ✅ shipped 2026-05-03 (`772df8b`).

**Wave 2 — Close stragglers** ✅ shipped 2026-05-03 (4 folders deleted; `mcp/vista/` + `cost_evaluation.py` repointed; `projects/README.md` refreshed).

**Wave 3 — Absorb-batch Tier 1 closure** (CURRENT)
1. `scheduling-engine-seed` Phase 0 (cardinality audit + scope confirmation).
2. `whatsapp-seed-absorption` Phase 0.
3. Then Tier 1.c + 1.d close — unblocks `imobi-scheduling-bot-creation`.

**Wave 4 — Escalate deferrals + cross-cutting**
1. File `send_message-consolidation` project (N=2 → preempt N=3).
2. `therapy-platform-wiring` Phase 0 (frontend api-call inventory at `products/therapy-platform/frontend/src/{hooks,pages}/`).
3. `mcp-server-fastmcp-switch` Phase 0 audit.

**Wave 5 — User-driven interrogation**
1. `project-history-ledger` §7 interrogation.
2. `adconnect-migration` Phase 0 audit (after user re-confirms scope).

---

## Outstanding parallel-agent work in working tree

- `M CLAUDE/projects.md` — linter-added authorship-discipline paragraph; belongs to whoever just landed it.
- `?? projects/session-review-baseline/` — parallel-agent project filing (predates this session); belongs to its filer.

Per the new `CLAUDE/projects.md` authorship-discipline rule, these stay uncommitted until their author commits them or you explicitly delegate.

---

## How to use this document

- **Each wave closes** → update or remove the closed items here, then refresh `projects/README.md` accordingly.
- **New projects filed** → add them under the right priority bucket; full status row goes in `projects/README.md`.
- **Deferrals escalated** → strike them from the P2 list and either file the follow-up project (move to P3) or apply inline.
- **This file lives at repo root** by user request despite the clean-folder principle's "repo root narrow" guidance — it's a transport doc, like `VISTA-API-MCP-GUIDE.md`.
