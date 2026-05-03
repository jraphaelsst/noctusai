# mcp-server-expansion — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project evolves. Revise phases, fold in optimizations, update §11.
>
> **Write for a zero-context reader.** Inline context in §1, quote the user in §2, name files with paths in §5, pair every §7 Open Question with an evidence-backed recommendation, make §10 commands copy-paste ready.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** Design captured → Phase 0 ready
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `KB § 06-AGENTS.md` (current MCP toolkit), `mcp/noctusai/README.md`, sibling reference at `~/Documents/repository/NoctusAI/whatsapp-google-scheduling/mcp_server/` (the smaller-but-cleaner business-logic MCP we're absorbing patterns + tools from), `projects/whatsapp-seed-absorption/PROJECT.md` (sibling project — the WhatsApp framework lift), `projects/mcp-scaffold-sql-templates-integration/PROJECT.md` (older MCP project — coordinate so we don't collide).
- **Project slug:** `mcp-server-expansion` — cross-cutting platform-infra concern. Lives at `projects/<slug>/`.

---

## 1. Context & Purpose

We have a 24-tool MCP at `mcp/noctusai/` (`server.py` + `cli.py` + `tools/*.py`). It's a **dev toolkit** — products / catalogs / KB sync / keeper / proposals / scaffold / refs / scans. Tools are flat-named (`noctusai_<action>`) and registered via a hand-coded dispatch map at `server.py:282-399`.

The sibling at `~/Documents/repository/NoctusAI/whatsapp-google-scheduling/mcp_server/` is a 12-tool **business-logic MCP** for a WhatsApp scheduling bot. Smaller surface, but cleaner abstractions: 3-segment dotted naming (`<vendor|platform>.<service>.<action>`), hierarchical registration (umbrella → service → leaf, each with `register(server)`), Pydantic in/out per tool with `Field(description=...)` for self-documenting MCP introspection, lazy `NoctusContext` dependency container for dual-callable (MCP + in-process + tests), settings shim for future repo extraction.

The user's mandate: **grow our MCP into the platform's wide-purpose toolkit.** The dev toolkit becomes one branch among many. Sibling's tools (Google Calendar, Google Maps, OpenAI audio/vision, scheduling, condominium, appointments, users, WhatsApp send-text) get absorbed into ours. The sibling's architectural patterns get adopted across the merged surface. MCP-first becomes a parallel mentality to AST-first: when we want to expose a capability to agents (Claude Code, future bots, future Vista CRM agents), it lands as an MCP tool first.

---

## 2. Confirmed constraints

Decisions the user made in the 2026-05-03 absorption-evaluation session.

- **MCP-first mentality** — *"the idea is for us to really evolve our mcp server. I'm talking about literally growing it, the dev toolkit should be a branch of it, we should bring the other mcp inside so we have a broader and even better wide-purpose toolkit, for more tools rather than only deving."* — Our MCP is the platform's unified toolkit. Dev tools, business-logic primitives, vendor adapters all live here. *(Drives §3 principle 1 + Phase 5 absorption.)*
- **MCP-first parallel to AST-first** — *"we are doing the ast-first, so it makes sense to also adopt the mcp-first mentality and expand it for a broader use."* — Becomes a methodology rule (when we expose a capability to agents, default surface is MCP). Captured in `KB § PATTERNS/` doc in Phase 6. *(Establishes the principle as durable, not project-scoped.)*
- **Settings shim — do it now** — *"lets do it now"* — Ship the settings shim as Phase 1 (smallest, highest-clarity, sets up the extraction path for future). *(Drives Phase 1 ordering.)*
- **Sibling MCP is "better architected" but for a different shape** — analyst's framing accepted: sibling is cleaner per tool because it's a 12-tool business-logic MCP; ours is a 24-tool dev toolkit. The patterns worth absorbing are the architectural ones (Pydantic schemas, dotted naming, hierarchical registration, settings shim, lazy context for business-logic tools). The dual-callable `_impl` split is **not** absorbed for our existing dev tools (they don't need it); it IS the pattern for future business-logic tools we add.

---

## 3. Design principles

1. **Backward-compatible at every phase.** Existing tool names (`noctusai_validate`, `noctusai_review`, etc.) keep working until an explicit deprecation phase. Adopting dotted names (`platform.dev.validate`, `platform.dev.review`) is additive — both names dispatch to the same function for one or more releases.
2. **Pydantic schemas for new tools immediately; existing tools migrate opportunistically.** New code lands with Pydantic in/out. Existing tools migrate when we touch them anyway (avoid mass-migrate-for-its-own-sake churn).
3. **Hierarchical registration replaces the flat dispatch map only when ≥1 namespace exists.** First namespace candidate: `platform.dev.*` (the existing toolkit). Adding sibling's vendor/platform groups (`google.*`, `openai.*`, `noctus.*` reframed as `platform.business.*`) drives hierarchical registration's payoff.
4. **Lazy `NoctusContext`-style container only for business-logic tools.** Dev tools stay stateless (filesystem + subprocess). Business-logic tools (the absorbed Calendar / Maps / WhatsApp / scheduling) get the container so they're dual-callable from the bot + MCP + tests. **Two registration models coexist** — that's fine; the alternative (force everything into a context) would over-engineer the dev surface.
5. **CLI dual-entrypoint stays.** Sibling has MCP-only; we have CLI + MCP sharing the same dispatch. That's a net win we keep through the expansion.
6. **No tool deprecation in this project.** Renames + dotted aliases yes; deletions no. A separate follow-up project handles deprecation timing once consumers (Claude Code config, CI, agents) have migrated.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

1. **Is the contract identical for every product?** YES — there is one MCP server consumed by all agents.
2. **Is the data source product-specific?** NO — the toolkit is platform-shared.
3. **Is the placement product-specific?** NO — single `mcp/noctusai/` location.
4. **Is the visibility / permission rule the same?** Per-tool variation (some dev-only, some platform-wide). Encoded in tool naming (namespaces) + future per-namespace allowlists.
5. **Does the seam already exist in seed?** YES — `mcp/noctusai/{server.py, cli.py, tools/}` is the existing seam. This project extends it.
6. **Default-on or opt-in?** DEFAULT-ON — the MCP server itself is always available; consumers (Claude Code, agents) opt into individual tools.

**Litmus — per-product code count this design requires:** [x] **0 lines** — pure cross-product / platform-infra concern. Lives entirely in `mcp/noctusai/` + KB.

**Phase plan implications:** §6 phases work in `mcp/noctusai/` and `KB`. **No phase walks through products.**

---

## 4. Scope

**In scope:**

- `mcp/noctusai/settings.py` shim re-exporting platform settings (Phase 1).
- Pydantic in/out schemas with `Field(description=...)` for new and touched tools (Phase 2).
- 3-segment dotted tool naming (`<umbrella>.<service>.<action>`), with backward-compat aliases (Phase 3).
- Hierarchical registration (umbrella → service → leaf, each with `register(server)`) replacing the flat dispatch map (Phase 4).
- Absorption of sibling MCP tools into ours (Phase 5):
  - `google.calendar.{create_event, get_event, list_events, delete_event}`
  - `google.maps.travel_estimate`
  - `openai.audio.transcribe`, `openai.vision.identify`
  - `platform.business.scheduling.suggest_slots`
  - `platform.business.appointments.intervals_for_date`
  - `platform.business.users.lookup_by_phone`
  - `platform.business.whatsapp.send_text`
- Lazy `NoctusContext`-style container at `mcp/noctusai/context.py` for business-logic tools added in Phase 5.
- KB pattern doc: `KB § PATTERNS/mcp-tool-conventions.md` (naming, registration, schemas, when to use context).
- New `CLAUDE.md §1` engineering rule: **MCP-first** — when exposing capability to agents, default surface is MCP.

**Out of scope (for now — with reason):**

- Tool deprecation timing — a separate follow-up project once consumers migrate.
- HTTP/SSE transport for remote MCP hosting — sibling's roadmap; not needed yet for our use cases.
- Per-tool observability (timing, error rates) — its own future project once we have a metrics sink.
- MCP-server extraction to standalone repo — the settings shim makes this future-feasible; the actual extraction is a separate project.
- The bot's `dev-team-support-bot/PROJECT.md` planned `noctus.dev.*` tools — that's a sibling project belonging to the WhatsApp repo, not ours.

---

## 5. Architecture / Data Model

### 5.1 Current state (here)

```
mcp/noctusai/
├── README.md
├── pyproject.toml
├── requirements.txt
├── catalog.md
├── cli.py              ← human CLI entry: --validate, --review, --build, --improvements, ...
├── server.py           ← MCP server entry: list_tools() (lines 50-269) + call_tool() (line 272) + _dispatch() map (lines 282-399)
├── tests/
└── tools/
    ├── ai_brain.py, analyzers.py, build.py, catalog.py, compliance.py, context.py,
    ├── cost_evaluation.py, diff.py, improvements.py, kb_sync.py, lgpd.py,
    ├── master_prompts.py, outline_python.py, outline_typescript.py, products.py,
    ├── proposals.py, recurrence.py, refs.py, review.py, scaffold.py, status.py,
    ├── testing.py, three_way_sync.py
```

24 tools, flat-named (`noctusai_validate`, `noctusai_analyze_patterns`, ...), JSON schema hand-coded inside `_tool()` blocks in `server.py`.

### 5.2 Target state (here, after this project)

```
mcp/noctusai/
├── README.md
├── pyproject.toml
├── catalog.md (+ doc updates)
├── settings.py          ← NEW (Phase 1) — re-export of platform settings; thin extraction-prep shim
├── context.py           ← NEW (Phase 5) — lazy dep container for business-logic tools
├── cli.py
├── server.py            ← simplified: register_all(server) call + run; dispatch removed
├── tests/
└── tools/
    ├── __init__.py      ← register_all(server) — calls every umbrella's register()
    ├── platform/
    │   ├── __init__.py  ← registers dev + business sub-umbrellas
    │   ├── dev/
    │   │   ├── __init__.py  ← registers all existing dev tools
    │   │   ├── validate.py, review.py, products.py, catalog.py, ... (existing tools moved + Pydantic-ified opportunistically)
    │   ├── business/
    │   │   ├── __init__.py  ← registers business tools (NEW from Phase 5)
    │   │   ├── scheduling/suggest_slots.py
    │   │   ├── appointments/intervals_for_date.py
    │   │   ├── users/lookup_by_phone.py
    │   │   └── whatsapp/send_text.py
    ├── google/
    │   ├── __init__.py
    │   ├── calendar/{create_event, get_event, list_events, delete_event}.py
    │   └── maps/travel_estimate.py
    └── openai/
        ├── __init__.py
        ├── audio/transcribe.py
        └── vision/identify.py
```

### 5.3 The there → here map (sibling MCP)

| There (`whatsapp-google-scheduling/mcp_server/`) | Here (`mcp/noctusai/tools/`) | Notes |
|---|---|---|
| `tools/google/calendar/create_event.py` | `google/calendar/create_event.py` | Pydantic-driven, dual-callable. Direct port + adapt to our credential storage (Phase 5). |
| `tools/google/calendar/get_event.py` | `google/calendar/get_event.py` | |
| `tools/google/calendar/list_events.py` | `google/calendar/list_events.py` | |
| `tools/google/calendar/delete_event.py` | `google/calendar/delete_event.py` | |
| `tools/google/maps/travel_estimate.py` | `google/maps/travel_estimate.py` | |
| `tools/openai/audio/transcribe.py` | `openai/audio/transcribe.py` | |
| `tools/openai/vision/identify.py` | `openai/vision/identify.py` | |
| `tools/noctus/scheduling/suggest_slots.py` | `platform/business/scheduling/suggest_slots.py` | Reframed under our `platform.business.*` namespace (sibling used `noctus.*` as platform marker; we use `platform.*`). |
| `tools/noctus/appointments/intervals_for_date.py` | `platform/business/appointments/intervals_for_date.py` | |
| `tools/noctus/users/lookup_by_phone.py` | `platform/business/users/lookup_by_phone.py` | |
| `tools/noctus/whatsapp/send_text.py` | `platform/business/whatsapp/send_text.py` | |
| `tools/noctus/condominium/travel_estimate.py` | (DROP) | Real-estate domain-specific; not generic. If a future product needs it, lives in that product, not in MCP. |
| `context.py` (`NoctusContext` lazy container) | `context.py` | Adapted to our settings + lib paths. |
| `settings.py` (re-export shim) | `settings.py` | Pattern; ours re-exports `noctusai_lib.config`. |
| `docs/architecture.md`, `docs/adding-a-tool.md` | `docs/` (NEW or extend existing `mcp/noctusai/README.md`) | Adapt to our naming + namespacing. |

### 5.4 Naming convention (post-Phase 3)

`<umbrella>.<service>.<action>` — three dotted segments, no exceptions.

- **`platform.dev.*`** — the current dev toolkit (validate, review, analyze_patterns, scan_recurrence, ...).
- **`platform.business.*`** — business-logic primitives any agent can compose.
- **`google.*`** — Google-vendor APIs (calendar, maps).
- **`openai.*`** — OpenAI-vendor APIs (audio, vision).
- Future namespaces by analogy (`anthropic.*`, `apple.calendar.*`, `mapbox.maps.*`, `vista.*`, etc.).

### 5.5 Backward-compat aliases

During Phase 3, every existing `noctusai_<action>` keeps working. We add the dotted alias next to it:

```python
# tools/platform/dev/validate.py
def validate(payload, ctx=None) -> ValidateOutput: ...

def register(server):
    server.tool(name="platform.dev.validate", description=...)(validate)
    server.tool(name="noctusai_validate", description=...)(validate)  # alias, deprecation in follow-up project
```

---

## 6. Implementation phases

### Phase 0 — Audit before any code lands

- [ ] Read every file in `mcp/noctusai/server.py` + every `tools/*.py` to confirm the 24-tool inventory.
- [ ] Read every file in sibling `mcp_server/` end-to-end. Confirm the absorption list in §5.3 matches reality.
- [ ] Verify `mcp/noctusai/cli.py` shares dispatch with `server.py` (so refactor in Phase 4 doesn't break the CLI).
- [ ] Identify any tool that already has Pydantic-ish schema (so Phase 2 doesn't double-work).
- [ ] Check `projects/mcp-scaffold-sql-templates-integration/` status to avoid colliding scope.
- [ ] If Phase 0 invalidates §6, **revise §6 in-place + log in §11**.

### Phase 1 — Settings shim (the user's "do it now")

- [ ] Create `mcp/noctusai/settings.py` re-exporting platform settings shape (mirror sibling's `mcp_server/settings.py:1-13`). Two-line file.
- [ ] Add docstring explaining intent: single source of truth until MCP extraction; when extracted, this becomes the source.
- [ ] Verify nothing breaks: `python mcp/noctusai/cli.py --validate` and `pytest mcp/noctusai/tests/`.
- [ ] Document in `mcp/noctusai/README.md`.

### Phase 2 — Pydantic in/out schemas pattern

- [ ] Pick 5 representative tools (suggested: `noctusai_validate`, `noctusai_analyze_patterns`, `noctusai_review`, `noctusai_catalog`, `noctusai_get_agent_context`). Convert their hand-coded JSON schemas in `server.py` to Pydantic input/output models inside the tool file itself.
- [ ] Ensure FastMCP's `server.tool()` introspects the Pydantic schemas correctly.
- [ ] Add Pydantic-schema rule to `mcp/noctusai/README.md` for new tools.
- [ ] Tests for the 5 migrated tools must pass.

### Phase 3 — Dotted naming + backward-compat aliases

- [ ] Add dotted names alongside existing flat names for the 5 Phase-2 tools (`platform.dev.validate`, etc.).
- [ ] Verify both names dispatch to the same function.
- [ ] Document the convention in `KB § PATTERNS/mcp-tool-conventions.md` (NEW pattern doc).
- [ ] Update `KB § 06-AGENTS.md` with the new naming.
- [ ] Update `CLAUDE.md §3 Map`.
- [ ] Verify `bash scripts/verify-kb-sync.sh` passes.

### Phase 4 — Hierarchical registration

- [ ] Create `tools/__init__.py::register_all(server)` per sibling pattern.
- [ ] Create `tools/platform/__init__.py` registering `dev` sub-umbrella.
- [ ] Move existing tool files into `tools/platform/dev/<service>/<action>.py` layout (or `tools/platform/dev/<action>.py` for tools that don't have a clear service grouping). Each file gets a `register(server)`.
- [ ] Replace the dispatch map in `server.py:282-399` with `register_all(server)`.
- [ ] Verify CLI still works (`cli.py` imports the same tool functions directly — should not need changes).
- [ ] All tests must pass.

### Phase 5 — Sibling tool absorption + business-logic context

- [ ] Create `mcp/noctusai/context.py` per sibling's `mcp_server/context.py` (lazy dep container; adapted to our paths).
- [ ] Port `google/calendar/*` (4 tools).
- [ ] Port `google/maps/travel_estimate`.
- [ ] Port `openai/audio/transcribe`, `openai/vision/identify`.
- [ ] Port `platform/business/{scheduling, appointments, users, whatsapp}/*` (4 tools, reframed namespace from sibling's `noctus.*`).
- [ ] Each ported tool: Pydantic in/out + dual-callable (`_impl` split) + `register(server)`.
- [ ] Tests for each ported tool.
- [ ] Document the lazy-context pattern in `KB § PATTERNS/mcp-tool-conventions.md`.

### Phase 6 — KB pattern doc + MCP-first principle

- [ ] Finish `KB § PATTERNS/mcp-tool-conventions.md` (naming, registration, Pydantic schemas, when to use context, dual-callable pattern, alias deprecation policy reference).
- [ ] Add `MCP-first` engineering rule to `CLAUDE.md §1 Engineering Philosophy` (parallel to `AST-first`).
- [ ] Update `KB § 06-AGENTS.md` and `KB § INDEX.md`.
- [ ] Three-way sync (KB ↔ CLAUDE.md ↔ memory).

### Phase 7 — Final verification + handoff

- [ ] `python mcp/noctusai/cli.py --validate` — green.
- [ ] `pytest mcp/noctusai/tests/` — green.
- [ ] `bash scripts/verify-kb-sync.sh` — green.
- [ ] `python mcp/noctusai/cli.py --review` — keeper observation only; triage findings.
- [ ] Scaffold the alias-deprecation follow-up project at `projects/mcp-tool-name-deprecation/`.

---

## 7. Open questions

1. **Top-level umbrella `platform.*` vs flatter `dev.*` / `business.*`?** Recommendation: keep `platform.*` so vendor-vs-platform distinction stays at the top level, parallel to `google.*` / `openai.*`. Decide before Phase 3 names land.
2. **`platform.business.*` vs `noctus.business.*`?** Sibling used `noctus.*` as platform marker; we have a `noctusai_lib`. Recommendation: `platform.*` (clearer separation). Decided before Phase 3.
3. **Existing `mcp-scaffold-sql-templates-integration/` project — collision risk?** Phase 0 reads its scope; if collision, coordinate ordering.
4. **Do MCP business-logic tools need access to product-specific DBs?** Recommendation: NO at first — context defaults to platform-shared resources. Per-product DB access is a future capability when the first business-logic tool needs it.

---

## 8. Dependencies & blockers

- **`projects/whatsapp-seed-absorption/`** — Phase 5's WhatsApp + Calendar / Maps absorption parallels its lib lifts. Coordinate so the MCP tools wrap the same lib code.
- **`projects/scheduling-engine-seed/`** — Phase 5's `platform.business.scheduling.suggest_slots` wraps the seed lib produced by that project.

---

## 9. Success criteria

- [ ] `mcp/noctusai/settings.py` exists and is referenced by tools that need settings.
- [ ] At least 5 existing tools migrated to Pydantic in/out schemas.
- [ ] Dotted names work alongside flat names (no breakage).
- [ ] Hierarchical registration replaces the dispatch map; CLI still works.
- [ ] All sibling tools listed in §5.3 (minus the dropped condominium one) are present and tested.
- [ ] `KB § PATTERNS/mcp-tool-conventions.md` exists and is linked.
- [ ] `CLAUDE.md §1` carries the new MCP-first principle.

---

## 10. How to use this plan

```bash
# Inspect current MCP
ls mcp/noctusai/tools/
python mcp/noctusai/cli.py --help

# Sibling reference (read-only)
ls ~/Documents/repository/NoctusAI/whatsapp-google-scheduling/mcp_server/tools/

# Verification
pytest mcp/noctusai/tests/
bash scripts/verify-kb-sync.sh
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial project drafted; user confirmed mcp-first growth mentality, settings shim as Phase 1, sibling tool absorption in Phase 5. | claude-opus-4-7 |

---

## 12. No-leftovers constraint

The sibling repo (`~/Documents/repository/NoctusAI/whatsapp-google-scheduling/`) WILL BE DELETED by the user once the absorption batch completes:

- **All sibling-path references in this PROJECT.md are execution-scoped** — vanish when this project closes per apply-inline-then-delete.
- **No KB doc landed during this project may reference sibling paths.** `KB § PATTERNS/mcp-tool-conventions.md` describes our MCP only.
- **No tool implementation in `mcp/noctusai/tools/` may import from or reference sibling paths.** Pattern: tool file is freshly authored on our conventions; sibling is the design reference, not the runtime dependency.
- **No `pyproject.toml` references sibling.**
| 2026-05-03 | Added §12 No-leftovers constraint. Cross-referenced `imobi-scheduling-bot-creation` as the natural first consumer of the absorbed `platform.business.*` MCP tools. | claude-opus-4-7 |

---

## 12. No-leftovers constraint

The sibling repo (`~/Documents/repository/NoctusAI/whatsapp-google-scheduling/`) WILL BE DELETED by the user once this absorption batch is complete.

**During execution**, sibling-path references in this PROJECT.md (the §5.3 there→here map and §10 commands) are acceptable as the executor's map.

**Hard rules:**
1. Code landed in `mcp/noctusai/` (tools, context, settings) MUST NOT contain string references to the sibling repo path.
2. KB pattern docs landed during this project (`KB § PATTERNS/mcp-tool-conventions.md`) MUST NOT cite sibling paths. Substance is paraphrased.
3. `mcp/noctusai/README.md` and `docs/` updates MUST NOT reference sibling.
4. When this project closes, this `PROJECT.md` is deleted (apply-inline-then-delete); sibling-path references die with it.
5. Verification at Phase 7: `grep -rIn "whatsapp-google-scheduling" mcp/noctusai/ KNOWLEDGE-BASE/` must return zero hits before sign-off.
