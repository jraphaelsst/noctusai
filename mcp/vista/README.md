# Vista CRM MCP Server

Typed MCP server wrapping the Vista Software / Loft CRM REST API. Phase 1
shipped 2026-05-03 (originating project `vista-api-mcp` closed + folder
deleted; see git history for the original PROJECT.md).

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
- **11 tools across 6 services** following the dotted naming convention
  per `KB § PATTERNS/mcp-tool-conventions.md`. The `access` column is the
  one to read before wiring a consumer — ✅ returns data today, 🔒 returns a
  typed 401 until Vista grants the per-method permission:

  | Tool | Vista route | Access | Notes |
  |---|---|---|---|
  | `vista.imoveis.list` | `/imoveis/listar` | ✅ | Paginated (≤50). 1,943 rows on `oneconsu`. Delta-syncable: `filter` on `DataAtualizacao`. |
  | `vista.imoveis.get` | `/imoveis/detalhes` | ✅ | `?imovel=` top-level. |
  | `vista.imoveis.list_filters` | `/imoveis/listarConteudo` | ✅ | Live enum values per field. |
  | `vista.usuarios.list` | `/usuarios/listar` | ✅ | 10 rows. **The ungated broker roster.** |
  | `vista.agencias.list` | `/agencias/listar` | ✅ | 1 row. |
  | `vista.clientes.list` | `/clientes/listar` | ✅ *(granted 2026-08-21)* | Paginated (≤50). **42,960 rows**, no `DataAtualizacao` ⇒ no delta sync. LGPD: Celular/DataNascimento/Sexo/EstadoCivil/Profissao (no CPF or address on this tenant). |
  | `vista.clientes.get` | `/clientes/detalhes` | ✅ *(granted 2026-08-21)* | `?cliente=` top-level. LGPD as above. |
  | `vista.corretores.list` | `/corretores/listar` | 🔒 401 | Substitute: `vista.usuarios.list`. |
  | `vista.diagnostics.probe` | — | ✅ | 8-row baseline; read `unexpected`, not `status`. |
  | `vista.diagnostics.list_known_endpoints` | — | ✅ | Static catalog + `probe_status`. |
  | `vista.diagnostics.show_calibrated_fields` | — | ✅ | Per-tenant safe field set. |

- **🔒 and ❌ are different answers, and the tools say which.** A gated tool
  returns `probe_status: "permission_gated"` with a typed 401 — meaning *ask
  Vista for the grant*, not *retry*, and not *this does not exist*. Routes
  that answer 404 (`/clientes/lead`, `/negociacoes/*`, and the ten other
  families in `vista.md § 4.6`) get **no tool at all**: a tool that can only
  ever report "no route" misrepresents the surface. See `vista.md § 4.2`.
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
- **The gated families calibrate lazily and stay un-armed until granted.**
  `get_cliente_fields` / `get_corretor_fields` return the floor `["Codigo"]`
  and — deliberately — do **not** cache a 401. So the first call after Vista
  grants the permission runs a real calibration pass instead of inheriting a
  guess, with no server restart needed. `show_calibrated_fields` reporting an
  empty `corretores` list therefore means "still gated", never "calibrated to
  nothing". **`clientes` was granted 2026-08-21** and its candidate set is now
  confirmed against a 200 (11 of 32 accepted — `vista.md § 4.2`); `corretores`
  remains 401 and its candidate set is still the unconfirmed public-doc
  superset, so do not copy that one into a consumer as known-good.
  🔴 Candidate sets must stay generous **supersets**: calibration only ever
  narrows, so a field absent from a CANDIDATE_* list can never be discovered
  no matter what the tenant exposes.
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
3. On `VistaFieldNotAvailable(fields=[X, Y, …])` → drop them ALL, retry.
   Vista names every rejected field in one 400, so this converges in two
   round-trips no matter how many fields the tenant refuses (measured
   2026-08-21 on `/clientes/listar`: 13 round-trips before, 2 after).
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
├── settings.py        — VistaSettings + get_settings() (composes _kit.settings)
├── types.py           — Pydantic In/Out schemas for the tool surface
├── server.py          — stdio MCP entry point (composes _kit.bootstrap)
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

**Not in this directory** — imported from the seed, never forked here:

- `VistaClient` + the 7-class error hierarchy + `extract_items` → `noctusai_lib.integrations.vista.client`
- `vista_*_to_showcase` normalizers → `noctusai_lib.integrations.vista.normalizers`
- `Showcase*` DTOs → `noctusai_lib.integrations.vista.types`
- `calibrator` + the CANDIDATE_* field sets → `noctusai_lib.integrations.vista.calibration`

(`client.py` / `normalizers.py` lived here in the original Phase 1 layout; commit
`b3e0b10f` moved them to the seed as part of the shared `mcp/_kit` refactor.
`calibration.py` followed 2026-08-03 — P2.0a of the
`social-wiring-imoveis-vista-2026-08` roadmap — because a product-side Vista sync
needs the same per-tenant field set, and a calibrator reachable only from the MCP
host forces every backend consumer to hardcode a field list instead.)
