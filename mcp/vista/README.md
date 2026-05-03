# Vista CRM MCP Server

Typed MCP server wrapping the Vista Software / Loft CRM REST API. Built
per `projects/vista-api-mcp/PROJECT.md` Phase 1 directive (2026-05-03).

The full Vista API contract lives at `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md`
— this README is the operations doc; the KB doc is the spec.

## What this Phase 1 ships

- **Typed client** ported from the ERP showcase adapter — `VistaClient`
  with the 7-class error hierarchy (`VistaError` base, `VistaConfigError`,
  `VistaUpstreamError`, `VistaPermissionDenied`, `VistaNotFound`,
  `VistaFieldNotAvailable`, `VistaTimeout`).
- **Per-tenant field-set calibration** (`calibration.py`) — lazy probe
  routine that addresses the gap noted in `vista.md § 6`: the showcase
  adapter uses hardcoded constants; this MCP discovers each tenant's
  safe field set by candidate-then-drop probing on first real call,
  cached per process.
- **8 tools across 6 services** following the dotted naming convention
  per `KB § PATTERNS/mcp-tool-conventions.md`:
  - `vista.imoveis.list` / `.get` / `.list_filters`
  - `vista.usuarios.list`
  - `vista.agencias.list`
  - `vista.clientes.list` (permission-gated → typed_error)
  - `vista.corretores.list` (permission-gated → typed_error)
  - `vista.diagnostics.probe` / `.list_known_endpoints` / `.show_calibrated_fields`
- **Pydantic In/Out per tool** with `Field(description=...)` so MCP
  introspection surfaces help text automatically.
- **Hierarchical registration** — each leaf module exports `HANDLERS` +
  `tool_descriptors()`; `tools/__init__.py` aggregates; `server.py`
  registers once at startup.

## What this Phase 1 does NOT ship (deferred per PROJECT.md)

- Phase 5 — keeper detector for guide ↔ adapter drift.
- Write tooling (POST endpoints) — out of scope for the read-only v1.
- Full integration tests against a live tenant — the `tests/` folder
  has a smoke test that confirms imports work; full live-probe tests
  belong in Phase 5.
- Token-cost telemetry hookup with `project-history-ledger` (PROJECT.md
  §7 Q4 — deferred to v2).

## Configuration

Per `vista.md § 1` and PROJECT.md §3 Design Principle #5, this MCP
reads its OWN per-tenant credentials — never inherits from the
platform `.env`. Resolution order:

1. Explicit args to `VistaSettings(...)`
2. Env vars `VISTA_BASE_URL` / `VISTA_API_KEY`
3. `mcp/vista/.env` (dev convenience; gitignored)

The client construction is **lenient** — missing config doesn't crash
the server. Tool calls return typed `VistaConfigError` instead.

## Run

```bash
# stdio MCP (typical)
python mcp/vista/server.py

# Smoke test — validate imports + tool registration without touching the network
python -m pytest mcp/vista/tests/ -q
```

To register the server with Claude Code or another MCP host, point the
host's MCP config at `python /absolute/path/mcp/vista/server.py`.

## Known Phase 1 limitations

- **`vista.diagnostics.probe` reports `/imoveis/listarConteudo` as
  `upstream_error`** even though the endpoint actually works via
  `vista.imoveis.list_filters`. The probe sends a generic `["Codigo"]`
  sentinel field set to every endpoint; `/imoveis/listarConteudo`
  rejects that with a 400 ("Não é possível filtrar por código nesse
  endpoint"). Phase 2 should switch to per-endpoint sentinels.
- **Nested-relation calibration is showcase-proven, not live-discovered.**
  The candidate sets in `calibration.py` use `{"Corretor": ["Nome", "Email"]}`
  for listar and `{"Corretor": ["Nome", "Email", "Fone"]}` for detalhes —
  shapes the showcase confirmed work on `oneconsu-rest`. Other tenants
  may accept additional sub-fields (`Creci`); a tenant that REJECTS
  even these would 400 with a sub-field name (e.g. `"Campo Creci"`),
  which `_drop_field` handles by pruning the relation's sub-list. Phase 2
  should add a proactive nested-sub-field discovery pass.
- **Calibration cache scope is per-process, not per-tenant-key.** If you
  rotate the tenant key without restarting the server, the cached
  field set may be stale. Restart the MCP server after rotation, or
  expose `Calibrator.reset()` via a future `vista.diagnostics.reset_calibration`
  tool.

## Per-tenant calibration

The Phase 4.5 hardening incident in the showcase project (UI showed
`[502] Vista respondeu erro 400` because the smoke probe never sent
the full field bundle in one request) proved that hardcoding the
public-doc field set is the wrong move. This MCP implements the
`vista.md § 6` calibration sketch:

1. Start from a CANDIDATE set (public-doc superset + showcase-known fields).
2. Send to the endpoint. On 200 → cache, return.
3. On `VistaFieldNotAvailable(field=X)` → drop X, retry.
4. Loop until 200 or the field count hits the floor `["Codigo"]`.

Inspect what the calibrator discovered for the active tenant via:

```
vista.diagnostics.show_calibrated_fields
```

To reset (e.g. after rotating the tenant key), restart the server.

## Files

```
mcp/vista/
├── __init__.py
├── settings.py        — VistaSettings + get_settings()
├── client.py          — VistaClient + 7-class error hierarchy + extract_items
├── normalizers.py     — vista_*_to_showcase mappers + helpers
├── types.py           — Pydantic In/Out schemas + showcase DTOs
├── calibration.py     — per-tenant field-set discovery (addresses vista.md § 6)
├── server.py          — stdio MCP entry point
├── tools/
│   ├── __init__.py    — aggregates HANDLERS + tool_descriptors() across leafs
│   ├── imoveis.py
│   ├── usuarios.py
│   ├── agencias.py
│   ├── clientes.py
│   ├── corretores.py
│   └── diagnostics.py
├── tests/
│   └── test_smoke.py  — import + registration smoke test
└── README.md          — this file
```
