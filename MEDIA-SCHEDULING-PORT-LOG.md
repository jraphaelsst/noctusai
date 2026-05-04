# Media Scheduling — Port Process Log (Resumed)

> **Where this file lives.** Worktree root: `noctusai-worktrees/media-scheduling-port-resume/`. The original (created at noc repo root in the main worktree) was lost during a parallel-agent collision — see `§ 1.6 Collision case study`. The architect/engineer methodology shipped 2026-05-04 says **engineers (subagents and dedicated long-running sessions) work in dedicated worktrees**; this file lives in the worktree root accordingly. At project close it moves with the rest of the project into `archive/projects/<date>/<NN>-media-scheduling-port/`.
>
> **What this file is.** Live narrative + decisions + observations + extracted knowledge + final reflections. Distinct from:
> - `projects/media-scheduling-port/PROJECT.md` — formal project doc (status, phases, sub-tasks, change log).
> - `projects/media-scheduling-port/findings.md` — durable curated findings (5-category structure per `feedback_knowledge_tracking.md`).
> - `mcp/noctusai/data/phase_learnings.db` (gitignored) — atomic per-phase records via `noctus.dev.phase_learning_log`.
> - `KB § PATTERNS/accept-with-rationale.md` — durable register of accept-with-rationale outcomes.

---

## 0 · Setup (resumed)

**Date:** 2026-05-03 (original setup) / 2026-05-04 (resume after collision)
**Source repo:** `/Users/rapha/Documents/repository/NoctusAI/whatsapp-google-scheduling/` — mature standalone FastAPI service: alembic migrations, WAHA webhook + worker, Google Calendar + Maps, OpenAI extractor, custom LID-aware first-inbound auth, HMAC verification, tool-call audit, structured logging.
**Target product:** `products/media-scheduling/` (to scaffold in Phase 1).
**Project doc:** `projects/media-scheduling-port/PROJECT.md` (in this worktree).
**Branch:** `media-scheduling-port-resume` (fresh; off `origin/main` at `062853b`). The original branch `media-scheduling-port` got repurposed by parallel work (its tip is methodology, not port code) — fresh name avoids confusion.
**Worktree:** `/Users/rapha/Documents/repository/NoctusAI/noctusai-worktrees/media-scheduling-port-resume/` — dedicated per the just-shipped *worktree-per-engineer* rule.
**Ports allocated:** backend `8096`, frontend `8130` (via `noctus.dev.available_ports`, original allocation).

### Interrogation summary (still valid)

| Topic | Decision |
|---|---|
| Slug / name | `media-scheduling` |
| Frontend | Thin admin (authorized users CRUD, appointment list, OAuth status) — same maturity as backend |
| DB | Supabase + numbered migrations (mirror via Supabase MCP) |
| Auth | SSO `authProvider` for admin; LID-aware first-inbound capture stays on the WAHA webhook path (accept-with-rationale) |
| Code shape | Port-onto-seed; "exactly the seed, nothing out of pattern" (user) |
| Source repo fate | Leave alone for now; revisit after green-bar verification |
| `mcp_server/` in source | Already absorbed in a prior session |
| `tool_call_audit` table | Use seed pattern (`AuditRecord` + `make_audit_writer`) |
| Webhook HMAC | Use `noctusai_lib.security.webhook_signatures` |
| Branching | Fresh branch off `origin/main` per branching methodology; **plus dedicated worktree per the new engineer-isolation rule** |
| Real conversation data | Source DB conversations are real WhatsApp ↔ OpenAI exchanges (not mock). Phase 2 preserves data fidelity. |

---

## 1 · Phase 0 — Seed-completeness audit ✅ (results from original session)

| Module | Status | Real adapters | Fake / test stand-in | Gap |
|---|---|---|---|---|
| `integrations.whatsapp` | ✅ runtime-ready | `WahaClient` (sync+async) | ❌ none | **G1** |
| `integrations.google_calendar` | ✅ runtime-ready (gold standard) | `GoogleCalendarServiceAccountAdapter`, `GoogleCalendarOAuthAdapter` | `FakeCalendarAdapter` | none |
| `integrations.google_maps` | ✅ runtime-ready (gold standard) | `GoogleMapsRoutingAdapter` | `StaticRoutingAdapter` | none |
| `integrations.llm` | ✅ runtime-ready | openai/anthropic/gemini auto-registered | `FakeProvider` | none — `response_format` covers structured output |
| `domain.chatbot` | ✅ runtime-ready (newer of two twins) | `RedisBufferClient` Protocol + real consumer | ❌ no Fake of `RedisBufferClient` | **G3** |
| `domain.conversation` | ⚠️ **OBSOLETE FORK** | same as chatbot | same | **G4** — only test-files reference; production uses chatbot |
| `domain.scheduling` | ✅ runtime-ready (pure logic) | engine + defaults | `ZeroTravelLookup` (default) | none |
| `security.webhook_signatures` | ✅ runtime-ready (pure crypto + dep factory) | `webhook_endpoint(...)` | n/a | none |
| `integrations.redis` | ✅ runtime-ready | `make_redis_client(redis_url)` | ❌ no Fake factory | **G2** |
| `domain.ai.tool_audit` | ✅ runtime-ready | `make_audit_writer(db, table_class)` | n/a (closure) | none |

### Gold-standard pattern (codified during the original Phase 0.5)

```
integrations/<name>/   (or domain/<name>/)
├── __init__.py          # Public surface + get_<name>_adapter(...) factory
├── types.py             # Value objects + <Name>Client Protocol
├── mappers.py           # Pure-function shape converters (when applicable)
├── fake_adapter.py      # Deterministic in-memory implementation
├── <vendor>_adapter.py  # Real-runtime adapter (one per backend)
├── credentials.py       # (when applicable) per-tenant credential resolver
└── settings.py          # (when applicable) Pydantic settings
```

Full pattern doc at `KB § PATTERNS/seed-fake-real-adapter.md` — already shipped in `origin/main` (the pattern doc + `KB INDEX.md` entry survived as the durable byproduct of the collision; the user's commit landed it before I resumed).

---

## 1.5 · Phase 0.5 — Seed-pattern backfill (re-execution)

The original Phase 0.5 work landed in the main worktree but got swept by the parallel-agent collision (see § 1.6). This re-execution lands in the dedicated worktree.

Same scope as original:

- **G1** — `integrations.whatsapp` Fake client + `WhatsAppClient` Protocol + `get_whatsapp_client(...)` factory + tests.
- **G2** — `integrations.redis` `make_fake_redis_client()` factory + tests + `fakeredis` dep.
- **G3** — `domain.chatbot.buffer` `make_in_memory_buffer_client()` re-export + tests.
- **G4** — Hard-delete `domain.conversation/` (production source) + `tests/domain/conversation/` (tests).
- **CLAUDE.md** — add §1 universal rule bullet for the Fake+Real pattern (KB pattern doc + INDEX entry already in `origin/main`; only this bullet is missing).
- **Memory** — already shipped in the previous session (memory survived the collision because it's outside git).

*(populated as execution lands — flipped to ✅ when tests green)*

---

## 1.6 · Collision case study (the meta-learning)

**What happened.** Original Phase 0.5 was executing in the main worktree at `/Users/rapha/Documents/repository/NoctusAI/noctusai`. In parallel, the user was doing methodology-formalization work on `architect-engineer-roles` branch in the **same worktree**. A branch-switch in the main worktree (reflog: `checkout: moving from progressive-refinement-archive to architect-engineer-roles`) discarded my uncommitted Phase 0.5 seed changes + project files (the new files were untracked, the modified files were reverted to origin/main state). My CLAUDE.md and INDEX.md edits got mixed in with the user's own pending edits to the same files.

**Survived (durable):**
- `~/.claude/projects/.../memory/` — all four memory updates landed (`feedback_seed_fake_real_pattern.md` new + amendments to `feedback_verify_seed_ships_it.md` + `feedback_recurrence_rule.md` + MEMORY.md index lines). Memory is OUTSIDE the git repo, so it survived.
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-fake-real-adapter.md` — sat as untracked file on the post-switch branch, copied into this worktree.
- `KB INDEX.md` entry for the pattern doc — committed by the user in their architect-engineer-roles work (pattern doc reference now lives at line 38 of the index, on `origin/main`).

**Lost:**
- Original `MEDIA-SCHEDULING-PORT-LOG.md` (root narrative log).
- Original `projects/media-scheduling-port/PROJECT.md` + `findings.md` (entire project folder).
- All G1-G4 seed code edits + new test files.
- G4 hard-delete of `domain.conversation` (restored).
- CLAUDE.md §1 universal rule bullet for the Fake+Real pattern.

**The fix that closed the gap.** During the same parallel work, the user shipped the **architect-engineer roles** + **`git worktree add` per engineer** rule — the structural fix this collision proved necessary. The new memory entry says: *"Architect (orchestrator) plans + dispatches + evaluates + stays-with-user; Engineers (subagents) build... `git worktree add` per engineer for true filesystem isolation when 2+ parallel."* That's the rule. This collision IS the case study that motivated formalizing it.

**Re-execution discipline applied:**
- Resume in dedicated worktree at `noctusai-worktrees/media-scheduling-port-resume/`.
- Fresh branch name to avoid name-collision with the repurposed `media-scheduling-port` branch.
- Per-phase commit cadence (originally I deferred all commits to project close — the collision proves this was the wrong cadence for parallel-active-work environments; commit-per-phase reduces blast radius of future collisions to one phase).

---

## 2 · Phase 1 — Scaffold

*(pending)*

---

## 3 · Phase 2 — Schema port

*(pending)*

---

## 4 · Phase 3 — Backend: WAHA webhook + buffer + worker

*(pending)*

---

## 5 · Phase 4 — Backend: scheduling engine + Calendar/Maps

*(pending)*

---

## 6 · Phase 5 — Frontend: thin admin

*(pending)*

---

## 7 · Phase 6 — Test port + green-bar verification

*(pending)*

---

## 8 · Phase 7 — Pattern compliance sweep + close

*(pending)*

---

## Knowledge bank — durable learnings

> Cumulative across phases. Curated subset → `findings.md`.

*(populated live)*

---

## My thoughts on the process

> *Final reflections — written at project close.*

*(pending)*

---

## Change log (this file)

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial setup (original session, lost in collision) | claude-opus-4-7 |
| 2026-05-04 | Re-created in dedicated worktree post-collision; setup + Phase 0 results + Phase 0.5 re-execution narrative + § 1.6 collision case study | claude-opus-4-7 |
