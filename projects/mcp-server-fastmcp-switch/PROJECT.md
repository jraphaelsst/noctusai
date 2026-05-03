# mcp-server-fastmcp-switch — Project Document

> **What this project is.** Phase 4 carry-forward from
> `projects/mcp-server-expansion/PROJECT.md`. The architectural switch
> from low-level `mcp.server.Server` to `mcp.server.fastmcp.FastMCP`
> + per-file `register(server)` pattern + relocation of 24 tool files
> into `mcp/noctusai/tools/noctus/dev/<action>.py`. Decomposed out of
> the parent project after Phases 0-3 + 6 + 7 shipped — the scope is
> too large + too cross-cutting to land in the same batch.
>
> **Why a separate project.** Phases 0-3 + 6 + 7 of mcp-server-expansion
> shipped the foundation (settings shim, Pydantic schemas, dotted
> aliases, KB pattern doc, MCP-first principle, alias deprecation
> plan). The FastMCP switch is genuinely a multi-hour focused-session
> rewrite touching: `server.py` (→ FastMCP outer), 50 tool
> registrations (→ per-file `register(server)` with wrapper functions
> for FastMCP signature introspection), 24 tool file paths (→
> `tools/noctus/dev/`), 25+ `cli.py` import lines, 30+ test imports.
> Doing this mid-batch alongside the parallel agent risks regressions
> + collisions.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** 🅿️ **PARKED** — fresh focused-session pickup. Predecessor `projects/mcp-server-expansion/` closes with Phases 4+5 deferred here (Phase 5 also gated on Tier 1 substrate per absorbed-projects-batch §7 round).
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `mcp-server-fastmcp-switch` (cross-cutting platform-infra)
- **Project location:** `projects/<slug>/` (cross-product / platform)
- **Predecessor:** `projects/mcp-server-expansion/PROJECT.md` (closed; absorbed via §11 entries; this project is its Phase 4 + 5 carry-forward).
- **Related docs:**
  - `KB § PATTERNS/mcp-tool-conventions.md` — naming, registration, Pydantic schemas, lazy context. The target shape this project realizes.
  - Sibling reference (alive at time of scaffold): `~/Documents/repository/NoctusAI/whatsapp-google-scheduling/mcp_server/` — exemplar for `register(server)` per leaf, FastMCP outer, lazy `NoctusContext`. **Sibling will be deleted by user after the absorption batch closes** — port the patterns into this project's notes before that happens.

---

## 1. Context & Purpose

The MCP server today (`mcp/noctusai/server.py`, ~480 lines after Phase
3 landed) ships 50 tools registered via:

- A flat dispatch map at `_dispatch()` (~117 lines) mapping tool name →
  lambda handler.
- A flat `list_tools()` async function (~245 lines) building Tool
  descriptors hand-coded as JSON dicts (with the Phase-2 exceptions
  using `model.model_json_schema()`).
- 6 Phase-3 dotted aliases coexisting with flat names via an `aliases`
  resolution map at the top of `_dispatch()`.

Sibling MCP server.py is **38 lines** because:
- It uses `FastMCP` (auto-introspects function signatures + Pydantic
  types).
- Each tool file exports `register(server)`; the umbrella
  `__init__.py` calls every leaf's `register`; `tools/__init__.py`
  exposes `register_all(server)` that the server calls once.
- File layout is `tools/<umbrella>/<service>/<action>.py` — shape
  encodes the dotted name.

Closing the gap = this project.

---

## 2. Confirmed constraints

- **Architectural target = sibling pattern** — confirmed in predecessor
  `mcp-server-expansion` §3 + §5.2. FastMCP outer, per-file
  `register`, hierarchical layout.
- **Naming locked = `noctus.*` umbrella** — predecessor §7 round
  decision; alias map already in place; this project enforces by
  organizing files as `tools/noctus/dev/<action>.py`.
- **CLI must keep working.** `cli.py` imports tool modules directly
  (`from tools.compliance import check_all_products`). Every import
  line breaks when files move. Phase 1 of THIS project = re-route
  every import to the new path.
- **Test imports update simultaneously.** `mcp/noctusai/tests/test_*.py`
  imports tool modules directly too. Same import-cascade work.
- **Sibling repo will be deleted by user.** Patterns to absorb (lazy
  `NoctusContext`, dual-callable `_impl` split for business-logic
  tools) live in `KB § PATTERNS/mcp-tool-conventions.md` already; this
  project doesn't re-import them.

---

## 3. Design principles

1. **Order matters: registration first, file moves last.** Add
   `register(server)` functions to each tool file IN PLACE first
   (server.py still imports them from current paths), verify tests
   pass, THEN move files. This isolates risk per phase.
2. **One umbrella at a time.** Migrate `noctus.dev.*` first (existing
   50 tools). `noctus.business.*` lands when Tier 1 substrate ships
   (carried from predecessor's Phase 5).
3. **CLI dual-entrypoint stays.** Sibling has MCP-only; we have CLI +
   MCP. Both keep working through every phase.

---

## 3a. Seed-first analysis

Cross-cutting platform-infra concern — pure `mcp/noctusai/` work, no
per-product code. Litmus: **0 lines** per-product. §6 phases work in
`mcp/noctusai/` only.

---

## 4. Scope

**In scope:**
- Switch `mcp/noctusai/server.py` outer from `Server` to `FastMCP`.
- Add `register(server)` to every tool file in `mcp/noctusai/tools/`.
- Create `tools/__init__.py::register_all(server)` + `tools/noctus/__init__.py` + `tools/noctus/dev/__init__.py`.
- Move `tools/<file>.py` → `tools/noctus/dev/<file>.py` (24 files).
- Update `cli.py` imports (25+ lines).
- Update test imports (30+ lines).
- Verify all 56 tools still register with same names; tests stay green.
- **Phase 5 of predecessor (sibling tool absorption — `google.*`,
  `openai.*`, `noctus.business.*`)** lands here once Tier 1 substrate
  (`whatsapp-seed-absorption` + `scheduling-engine-seed`) ships. Until
  then, scaffolding only — no actual ports.

**Out of scope:**
- Tool deprecation timing — `projects/mcp-tool-name-deprecation/`.
- HTTP/SSE transport — sibling's roadmap; not needed yet.
- Per-tool observability (timing, error rates) — own future project.

---

## 5. Architecture / Data Model

### 5.1 Source: predecessor's §5.2 target tree

```
mcp/noctusai/
├── server.py            ← simplified: FastMCP + register_all(server) + run
├── settings.py          ← shipped by predecessor Phase 1
├── context.py           ← NEW (Phase 5 from predecessor) — lazy NoctusContext for business-logic tools
├── cli.py               ← updated imports
└── tools/
    ├── __init__.py      ← register_all(server)
    ├── noctus/
    │   ├── __init__.py  ← registers dev + business sub-umbrellas
    │   ├── dev/
    │   │   ├── __init__.py  ← registers all dev tools
    │   │   └── <action>.py  ← 24 tool files moved here, each with register(server)
    │   └── business/
    │       ├── __init__.py
    │       ├── scheduling/suggest_slots.py
    │       ├── appointments/intervals_for_date.py
    │       ├── users/lookup_by_phone.py
    │       └── whatsapp/send_text.py
    ├── google/calendar/{create_event, get_event, list_events, delete_event}.py
    ├── google/maps/travel_estimate.py
    └── openai/audio/transcribe.py + openai/vision/identify.py
```

### 5.2 Tool count target

- 50 dev tools + 6 dotted aliases (predecessor inheritance) = **56**.
- Plus 10 business + vendor tools when Tier 1 substrate ships = **66**.

---

## 6. Implementation phases

### Phase 0 — Audit before any code lands

- [ ] Re-confirm 50-tool inventory matches `server.py` dispatch map at this project's start (parallel agent may have added more).
- [ ] Re-read sibling `mcp_server/` end-to-end. Confirm `_impl` split + `noctus_context()` cm pattern is still the absorbed shape.
- [ ] Re-confirm CLI's tool-module imports (greppable: `^from tools\.`).
- [ ] Re-confirm test files' tool-module imports.
- [ ] If §6 needs revising, revise in-place + log in §11.

### Phase 1 — register(server) in place (no file moves)

- [ ] Each tool file gains a `register(server)` function that calls `server.tool(name=..., description=...)(wrapper_fn)`. For tools without a Phase-2 Pydantic Input, write a minimal one inline. For tools with one, use it.
- [ ] Wrapper functions inside `register()` adapt the existing tool function signature to FastMCP's introspection requirement.
- [ ] Tests stay green.
- [ ] server.py STILL uses old dispatch — register() is just declared, not yet invoked.

### Phase 2 — server.py switch to FastMCP outer + register_all

- [ ] `server.py` rewritten: imports `FastMCP`, creates server, calls `register_all(server)`, runs over stdio.
- [ ] `tools/__init__.py::register_all(server)` calls each tool file's `register(server)`.
- [ ] Old dispatch map removed.
- [ ] `_tool()` helper retired.
- [ ] Smoke test: `python -m mcp.noctusai.server` starts; `tools/list` returns all 56 tools with same names + schemas.

### Phase 3 — File relocation (cli + tests cascade)

- [ ] Move each `tools/<file>.py` → `tools/noctus/dev/<file>.py` via `git mv` (preserves history).
- [ ] Update `cli.py`: every `from tools.<mod> import <fn>` → `from tools.noctus.dev.<mod> import <fn>`.
- [ ] Update `mcp/noctusai/tests/test_*.py` imports.
- [ ] Ensure `tools/__init__.py` + `tools/noctus/__init__.py` + `tools/noctus/dev/__init__.py` exist.
- [ ] CLI smoke: `--help`, `--validate`, `--status`, `--review`.
- [ ] Tests green.

### Phase 4 — Substrate absorption (carries the predecessor's deferred sibling-tool absorption work)

GATED ON: `projects/whatsapp-seed-absorption/` + `projects/scheduling-engine-seed/` close (per absorbed-projects-batch §7 deferral). Until both ship, this phase stays parked.

- [ ] Create `mcp/noctusai/context.py` — lazy `NoctusContext` cm (sibling pattern).
- [ ] Port `google.calendar.{create_event, get_event, list_events, delete_event}` (4 tools).
- [ ] Port `google.maps.travel_estimate`.
- [ ] Port `openai.audio.transcribe` + `openai.vision.identify`.
- [ ] Port `noctus.business.{scheduling.suggest_slots, appointments.intervals_for_date, users.lookup_by_phone, whatsapp.send_text}` (4 tools).
- [ ] Each ported tool: Pydantic In/Out + dual-callable `_impl` + `register(server)`.
- [ ] Tests for each ported tool.
- [ ] No sibling-path leaks (`grep -rIn "whatsapp-google-scheduling" mcp/noctusai/` returns 0).

### Phase 5 — Final verification + handoff

- [ ] `python mcp/noctusai/cli.py --validate` green.
- [ ] `pytest mcp/noctusai/tests/` green.
- [ ] `bash scripts/verify-kb-sync.sh` green.
- [ ] `python mcp/noctusai/cli.py --review` triage.
- [ ] Trigger `projects/mcp-tool-name-deprecation/` Phase 0 (consumers should now have migrated; alias retirement can begin).

---

## 7. Open questions

Surfaced at Phase 0 kickoff of THIS project (not the predecessor — the predecessor's §7 is closed).

1. **Has the parallel agent added more tools to `server.py` between predecessor close and this project start?** Phase 0 audit confirms inventory.
2. **Is `git mv` for the 24 file relocations safe per the pre-commit hook?** First Phase 3 attempt should verify no hook surprises.
3. **Do any existing tool files have intra-tool imports** (e.g. `tools.review` importing `tools.compliance`)? Phase 0 audit confirms; if yes, those re-route too.

---

## 8. Dependencies & blockers

- **Predecessor `projects/mcp-server-expansion/` closed** — confirmed at scaffold time.
- **Phase 4 of THIS project gates on Tier 1 substrate** — `whatsapp-seed-absorption` + `scheduling-engine-seed` close.
- **Sibling repo deletion timing** — patterns absorbed into KB already; sibling can vanish without affecting this project's Phase 1-3.

---

## 9. Success criteria

- `mcp/noctusai/server.py` ≤80 lines (down from current ~480).
- All 56 dev tools register via per-file `register(server)`.
- All 10 substrate-dependent tools (`google.*` + `openai.*` + `noctus.business.*`) shipped via Phase 4 once gating substrate lands.
- CLI smoke + pytest + KB sync all green.
- Zero sibling-path leaks under `mcp/noctusai/` post-Phase 4.
- Trigger `mcp-tool-name-deprecation` Phase 0 — alias retirement window opens.

---

## 10. How to use this plan

```bash
# Re-audit at start
ls mcp/noctusai/tools/
grep -rln "^from tools\." mcp/noctusai/cli.py mcp/noctusai/tests/

# Sibling reference (read-only; check it still exists)
ls -d ~/Documents/repository/NoctusAI/whatsapp-google-scheduling/mcp_server/ 2>/dev/null

# Phase verification
./venv/bin/python -m pytest mcp/noctusai/tests/
./venv/bin/python mcp/noctusai/cli.py --validate
bash scripts/verify-kb-sync.sh
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project scaffolded** as carry-forward from `projects/mcp-server-expansion/` (which closed with Phases 0-3 + 6 + 7 ✅). Architecture target inherited from predecessor §5.2; phase plan re-decomposed into six numbered phases — see §6. None executed yet; status PARKED awaiting focused-session pickup. | claude-opus-4-7 |

---

## 12. No-leftovers constraint

The sibling repo (`~/Documents/repository/NoctusAI/whatsapp-google-scheduling/`) is on the user's deletion list once the absorption batch closes.

- Phases 1-3 of this project DO NOT depend on the sibling repo at all (just refactor of our own MCP).
- Phase 4 (substrate absorption) does — but only as a design reference. The implementation patterns are already absorbed into `KB § PATTERNS/mcp-tool-conventions.md` (committed separately).
- No code landed by this project may reference sibling paths. Phase 4 verification grep enforces.
