# noctus-supabase-advisors-proxy — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 📋 **READY FOR EXECUTION.** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineer Z's imobi P3 close (commit `929b28b`) hit Anthropic tool-result cap on Supabase MCP `get_advisors`: security 138KB + performance 393KB outputs are above the cap. Inevitable for every product schema; needs a server-side filter proxy.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `noctus-supabase-advisors-proxy`

---

## 1. Context & Purpose

The Supabase MCP exposes `get_advisors(project_id, type)` returning ALL advisors at that project's scope. For an active project, this is hundreds of rows × thousands of bytes each — easily 100KB-500KB. Anthropic tool-result cap blocks the response.

Engineer Z worked around by reading the JSONL from disk + filtering. Not a durable solution — every future product schema audit hits the same wall.

**Right fix**: a noc-side proxy MCP tool that:
1. Accepts a `schema=` filter (so the imobi-scheduling audit returns only imobi rows).
2. Optionally accepts severity filter (`ERROR`, `WARN`, `INFO`).
3. Optionally filters out `unused_index` for schemas <1 day old (no traffic baseline).

## 2. Confirmed constraints

- **Supabase MCP `get_advisors`** is unchanged — we wrap it.
- **noc-side MCP** at `mcp/noctusai/tools/noctus/dev/supabase_advisors.py`.
- **Must accept `worktree_path`** per `feedback_mcp_write_tools_resolve_caller_root.md` (though this is read-only; still good convention).
- **Pydantic-shaped return** — `list[Advisor]` with `severity`, `category`, `message`, `schema`, `table`, `name`.

## 3. Design principles

1. **Filter server-side**. The whole point — don't ship 500KB just to slice it down to 5KB.
2. **Sensible defaults**: drop `unused_index` for fresh schemas; include all by default.
3. **Single MCP call, multiple downstream uses**: audit at product close, drift detection at master-tree retrospective, security review at LGPD pass.

## 3a. Seed-first analysis

- **Cross-product?** YES — every product schema audit needs this.
- **Seed home?** `mcp/noctusai/tools/noctus/dev/supabase_advisors.py`.
- **Per-product code count?** 0.

## 4. Scope

- **In scope:**
  - New MCP tool `noctus.dev.supabase_advisors(schema=None, severity=None, type="security"|"performance"|"all")`.
  - Server-side filter on schema/severity/category.
  - Pydantic Advisor model.
  - Tests with fixture JSONL.
- **Out of scope:**
  - Caching (advisor results are fresh-on-call).
  - Auto-resolution suggestions (advisors already include them in `message`).

## 5. Architecture / Data Model

```python
# mcp/noctusai/tools/noctus/dev/supabase_advisors.py
class AdvisorResult(BaseModel):
    severity: Literal["ERROR", "WARN", "INFO"]
    category: str  # e.g. "unindexed_foreign_keys"
    schema: str | None
    table: str | None
    name: str
    message: str
    suggested_action: str | None

@server.tool(name="noctus.dev.supabase_advisors")
async def supabase_advisors(
    *,
    schema: str | None = None,
    severity: list[Literal["ERROR", "WARN", "INFO"]] | None = None,
    type: Literal["security", "performance", "all"] = "all",
    drop_unused_index_for_new_schemas: bool = True,
    worktree_path: str | None = None,
) -> list[AdvisorResult]:
    """Filtered advisor surface — avoids Anthropic tool-result cap."""
    # Call Supabase MCP get_advisors via subprocess/HTTP-call to MCP-stdio
    # Filter client-side (since we control the wrap)
    # Return Pydantic list
```

## 6. Implementation phases

### Phase 0 — Audit Supabase MCP advisor shape

- [ ] Read existing get_advisors response from a real call (the imobi schema audit) — confirm field set + filter targets.
- [ ] Confirm proxy can call Supabase MCP from inside noctus MCP without recursion issues.

### Phase 1 — Ship the tool

- [ ] Author `mcp/noctusai/tools/noctus/dev/supabase_advisors.py`.
- [ ] Register in tools/__init__.py.
- [ ] Tests with fixture: 200-row advisor dump → filtered to 5 ERROR + 12 WARN rows.

### Phase 2 — Wire + close

- [ ] Update `KB § PATTERNS/mcp-tool-conventions.md` with the new tool entry.
- [ ] Update `feedback_supa_mcp_proactive.md` memory entry to mention the wrapper.
- [ ] Smoke: call from worktree with `worktree_path=`; confirm filtered output.

## 7. Open questions

- Q1: How does noctus MCP call Supabase MCP? **Default rec**: HTTP shimmed via the existing Supabase MCP server (it accepts JSON-RPC over stdio). May need a `supabase_mcp_client.py` helper. Worth a small spike at Phase 0.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [ ] Tool ships + tests green.
- [ ] Calling `noctus.dev.supabase_advisors(schema="imobi_scheduling")` returns ≤10KB filtered list.
- [ ] Anthropic tool-result cap never blocks again on advisor reads.

## 10. How to use this plan

Single-engineer dispatch. Mechanical MCP-tool authoring + Pydantic + tests.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer Z's imobi P3 close hit Anthropic tool-result cap on Supabase MCP `get_advisors` (security 138KB, performance 393KB). Inevitable for every product schema; needs server-side filter proxy. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
