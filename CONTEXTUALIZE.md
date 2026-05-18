# CONTEXTUALIZE.md — fresh-agent onboarding map

> **Trigger.** The user said "contextualize" / "please contextualize" to a clean-context agent, OR you genuinely don't know what this platform is. Read this **once**, top to bottom, follow the map, then do the task the user asked. **If you are already working / already oriented: you should not be here — `CLAUDE.md`'s NEW-SESSION-CONTEXTUALIZATION section told you to skip. Re-reading this wastes tokens.**
>
> This file is a **map and a mental model**, not a copy of the docs. It points; the targets hold the depth. After this + the linked reads you are contextualized — everything else loads on-demand via `CLAUDE.md` §2/§3 + `KNOWLEDGE-BASE/INDEX.md`.

---

## 1. What this platform is (30 seconds)

NoctusAI is a **multi-product platform built on a shared seed**. ~10 products (ERP, therapy, social-wiring, PF, daily-life, core, …) all inherit one backend factory (`create_product_app()`) + one frontend factory (`createProductApp()`) + a shared library (`noctusai_lib`) + a shared seed framework. Products are thin; the seed is the spine. There is a heavy, **living methodology** governing how work is done — it is codified in docs and it improves itself every session.

## 2. Read in this order (the core set)

Each line: *what to read → what you'll know after.* Stop when you have enough for the task; the rest is on-demand.

1. **`CLAUDE.md` §1 (Universal rules)** → the non-negotiable behavioral contract you obey every turn. §2 (The Map) + §3 (When to read what) → how to find any depth doc on-demand. *(It's auto-loaded; actually read §1, don't skim.)*
2. **`KNOWLEDGE-BASE/AGENT-CONTEXT.md`** → fresh-session orientation (the existing first-stop).
3. **`KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md`** → the product list, schemas, ports, stack — *what exists*.
4. **`KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`** → the foundational principles — *how we think* (seed-first rationale, no-silent-errors, always-hardening, codebase-is-source-of-truth).
5. **`KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md`** → how products inherit the seed; the named seams; the "verify-the-seed-ships-it" test. The single most load-bearing architectural rule.
6. **`KNOWLEDGE-BASE/INDEX.md`** → the full KB map. You don't read KB cover-to-cover; you grep/route here when a task needs depth.
7. **`MEMORY.md`** (memory index, auto-loaded) → the accumulated feedback/working-agreement rules — one line each, expand the relevant ones on demand.

**Conditional (read only if the task is that):**
- Project / dispatch / branching work → `CLAUDE/projects.md` + `KB § PATTERNS/project-execution.md` + `KB § PATTERNS/branching-and-merging.md` (esp. §21 collision-class branching).
- You will dispatch or be dispatched as an engineer → `.claude/agents/engineer-default.md`.
- Backend/frontend code → `CLAUDE/backend.md` / `CLAUDE/frontend.md` + the matching `KB § PATTERNS/` + `KB § backend|frontend/0X-*.md`.
- New product / absorb / deploy → the `CLAUDE.md` §3 trigger-phrase row points to the exact guide.

## 3. How we work — the mental model you must hold before touching anything

- **Seed first, always.** Never hand-fork what the seed provides; flow customizations through named seams. Verify the seed actually ships a thing (`__init__.py` + real adapter) before consuming it.
- **The methodology is living and self-improving.** It is never finished. Every execution is a *training pass*: spotted improvements are announced **loudly** in-the-moment (`**Methodology improvement spotted**`), implemented before the in-flight work ships, and three-way-synced. Silent-but-correct self-improvement breaks the contract.
- **Three-way sync.** Any rule/methodology change lives in **KB ↔ CLAUDE.md (or CLAUDE/topical) ↔ memory** the same session. Docs are layered: `CLAUDE.md` = router; `CLAUDE/<topic>.md` = topical rules; `KNOWLEDGE-BASE/` = depth; `MEMORY.md` = index.
- **Codebase is source of truth.** Docs/memory/another agent's report drift. Before acting on any claim, verify it against the tree (`git status`/`Read`/`pytest`). Doc disagrees with code → code wins, fix the doc same change.
- **No silent errors. No stale work.** No `except: pass`, no unverified "✓", no deferred item without a named destination. Clear-path deferrals / accept-with-rationale / findings / AI↔AI comms are resolved **in-flight, same commit** — not parked for later (`KB § PATTERNS/project-execution.md §2.13`).
- **Branching-first.** Parallelizable work → isolated worktrees + parallel engineer dispatch; the architect plans+dispatches+stays-with-user, engineers build. Merge cleanliness is decided at *dispatch* time (collision-class C1/C2/C3, `KB §21`).
- **AST-first** for code edits (libcst/ts-morph/tree-sitter) — never regex/sed on source.
- **Fix-on-contact.** Bumped into pre-existing debt while doing other work → fix it in-flight, then surface problem+root-cause+solution. Surface-only is forbidden.
- **Commit discipline.** Never auto-commit/push except project gates; commit only your own authored work; verify staged set; main pushes are R4 human-gated (present → explicit go → execute).
- **MCP keep-list:** `noctusai` + `supabase` only. Any other MCP/skill needs explicit user approval.
- **Symbol-first** for AI-intended docs (the glossary is `KB § PATTERNS/doc-symbology.md`) — but NOT for first-paragraph context, quoted-user, errors, commits.
- **The user thinks-with the architect.** Stay available; engineers (subagents) do heavy lifting in isolation.

## 4. Trigger phrases that change behavior (recognize these in the user's prompt)

`create/scaffold/absorb a product` · `branch this / branch X` · `put X online / deploy / spin up` · `absorb the X workspace` · `two sessions / architect-operator` · `contextualize` (this file) · `c-push` · `/loop` `/schedule` `/security-review` · "what cleanup is urgent?" (→ `noctus.hound.scan`). The exact routing for each is in `CLAUDE.md` §3.

## 5. You're contextualized

You now know: what the platform is, the core docs + where depth lives, the non-negotiable mental model, the trigger phrases. **Proceed with the user's actual task.** Pull depth on-demand via `CLAUDE.md` §2/§3 + `KNOWLEDGE-BASE/INDEX.md` — do not pre-read everything (that wastes tokens; the methodology values lean context). Welcome aboard.

> *Provenance: this ramp is **clean-context-agent-verified** (not asserted) — first validated 2026-05-18 by dispatching a zero-context agent given only "please contextualize"; it passed (oriented after ~2 files) and surfaced 2 doc-drift bugs, fixed in-flight. Re-run that self-test after material changes to the core onboarding docs (memory `feedback_new_session_contextualization`).*
