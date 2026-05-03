# MCP tool conventions

> Conventions for authoring tools in `mcp/noctusai/`. Lands during
> `projects/mcp-server-expansion/` Phase 3 (naming + Pydantic) and Phase 6
> (the principle); `noctusai_lib`-side patterns referenced inline.
>
> **Status:** active. Backward-compat aliases coexist with legacy flat
> names until a separate alias-deprecation project retires them.

---

## 1. Naming — three dotted segments

`<umbrella>.<service>.<action>` — three segments, no exceptions.

- **`noctus.dev.*`** — the platform dev toolkit (validate, review,
  analyze_patterns, scan_recurrence, …). The "what we currently have."
- **`noctus.business.*`** — business-logic primitives any agent can
  compose (scheduling, appointments, users, whatsapp). Lands in Phase 5
  of `projects/mcp-server-expansion/` after `noctusai_lib` substrate
  ships.
- **`google.*`** — Google-vendor APIs (calendar, maps).
- **`openai.*`** — OpenAI-vendor APIs (audio, vision).
- Future namespaces by analogy (`anthropic.*`, `apple.calendar.*`,
  `mapbox.maps.*`, `vista.*`, etc.).

Rule of thumb for `noctus.*` vs `<vendor>.*`: a tool lives under a
vendor namespace when the **capability itself** is vendor-specific
(Google Calendar IDs, OAuth scopes, OpenAI completions API). Tools we
*own* that happen to call out to a vendor under the hood live under
`noctus.*` — the vendor is an implementation detail.

### Backward-compat aliases

During Phase 3 of the expansion, every existing `noctusai_<action>`
keeps working. We add the dotted alias next to it; both names dispatch
to the same handler:

```python
# server.py
_tool("noctusai_validate", "...", model=ValidateInput),
_tool("noctus.dev.validate", "Dotted alias for noctusai_validate.", model=ValidateInput),
```

```python
# _dispatch()
aliases = {"noctus.dev.validate": "noctusai_validate", ...}
canonical = aliases.get(name, name)
handler = dispatch_map.get(canonical)
```

A separate follow-up project retires the flat names once consumers
(Claude Code config, CI, agents) have migrated.

---

## 2. Pydantic In/Out per tool

New tools land with `XxxInput(BaseModel)` and `XxxOutput(BaseModel)`
classes **inside the tool file itself**. The shape is:

```python
# tools/<area>/<action>.py (Phase 4 hierarchical layout)
# or tools/<flat>.py (current layout)
from pydantic import BaseModel, Field

class XxxInput(BaseModel):
    foo: str = Field(description="What this is for.")

class XxxOutput(BaseModel):
    result: dict[str, Any] = Field(description="Tighten as call sites stabilize.")
```

`server.py`'s `_tool(name, desc, model=XxxInput)` auto-generates the
JSON schema via `Model.model_json_schema()`. No hand-coded property
dicts.

**Rules:**
- New tools: Pydantic In + Out from day one.
- Existing tools: migrate **opportunistically** when touched (don't
  mass-migrate for its own sake).
- Output models start minimal (`dict[str, Any]` for dynamic surface)
  and tighten as the shape stabilizes. The README documents the
  pattern as deliberate, not lazy.

### Worked examples (Phase 2 landing)

The first 5 migrated tools each carry both classes:
- `tools/context.py` — `AgentContextInput`/`Output`,
  `ProductContextInput`/`Output`.
- `tools/compliance.py` — `ValidateInput`/`Output`, `ValidateIssue`.
- `tools/analyzers.py` — `AnalyzePatternsInput`/`Output`,
  `DuplicatedFunction`, `InlineHookIssue`.
- `tools/review.py` — `ReviewInput`/`Output`, `ReviewMode`.
- `tools/catalog.py` — `CatalogInput`/`Output`.

---

## 3. Hierarchical registration (lands in Phase 4)

Each leaf module exports `register(server)`; sub-umbrella `__init__.py`
calls every leaf's `register`; the top-level `tools/__init__.py`
exposes `register_all(server)` that the FastMCP server calls once at
startup.

```python
# tools/noctus/dev/validate.py (Phase 4 target shape)
def register(server):
    server.tool(name="noctus.dev.validate", description=...)(validate)
    server.tool(name="noctusai_validate", description=...)(validate)  # alias
```

This replaces the flat dispatch map at `server.py:282-399`. Phase 4
also updates `cli.py` import lines (the CLI does NOT share dispatch —
it imports tool modules directly).

---

## 4. Lazy `NoctusContext`-style container — **only for business-logic tools**

Dev tools stay stateless (filesystem + subprocess). Business-logic
tools get a `NoctusContext` lazy-dep container so they're trivially
callable from three modes:

1. **From the MCP server** — FastMCP creates a context, calls the
   tool, closes.
2. **In-process from a product** — the product creates a context with
   its own DB session.
3. **From tests** — tests construct a context with fakes/mocks
   injected.

The dual-callable shape:

```python
def my_tool(payload: MyInput, ctx: NoctusContext | None = None) -> MyOutput:
    if ctx is not None:
        return _impl(payload, ctx)
    with noctus_context() as owned_ctx:
        return _impl(payload, owned_ctx)
```

Two registration models coexist — that's fine; forcing dev tools into a
context would over-engineer the dev surface.

---

## 5. Settings shim

`mcp/noctusai/settings.py` re-exports `BaseAppSettings` from
`noctusai_lib.config.settings` as `Settings`, plus a local
`lru_cache(maxsize=1)`-backed `get_settings()` singleton. The lib
**doesn't ship a global factory by design** — per-product
`Settings(BaseAppSettings)` is the documented pattern, and a
lib-level singleton would force every consumer to share one across
processes. The MCP-scoped factory in the shim is the right shape.

When the MCP gets extracted to its own repo, this shim becomes the
source — every consumer (the platform, future bots, …) reads its own
`.env` against the same shape.

---

## 6. CLI dual-entrypoint stays

Sibling business-logic MCPs are MCP-only. We keep the CLI alongside the
MCP because the CLI is a real consumer (humans + scripts +
pre-commit hooks all use it). Both entrypoints share tool functions,
not the dispatch map.

---

## 7. MCP-first principle

When we want to expose a capability to agents (Claude Code, future
bots, future Vista CRM agents), the **default surface is MCP**. AST-first
is its sibling principle (CLAUDE.md §1, KB § PATTERNS/ast.md): mechanical
edits go through AST tools; agent-exposable capabilities go through MCP
tools.

This rule is in CLAUDE.md §1 (memory: `feedback_mcp_first.md`); this doc
is its depth pointer.

---

## 8. Coexistence rules

- **Backward-compatible at every phase.** Existing tool names keep
  working until an explicit deprecation project retires them.
- **Hierarchical registration replaces the flat dispatch map only when
  ≥1 namespace exists.** First namespace candidate: `noctus.dev.*` (the
  existing toolkit). Adding sibling vendor/platform groups
  (`google.*`, `openai.*`, `noctus.business.*`) drives the payoff.
- **No tool deprecation in Phase 3.** Renames + dotted aliases yes;
  deletions no. A separate follow-up project handles deprecation
  timing.
