# Vista CRM MCP Server

Typed MCP server wrapping the Vista Software / Loft CRM REST API. Phase 1
shipped 2026-05-03 (originating project `vista-api-mcp` closed + folder
deleted; see git history for the original PROJECT.md).

The full Vista API contract lives at `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md`
— this README is the operations doc; the KB doc is the spec.

## What this Phase 1 ships

- **Typed client** ported from the ERP showcase adapter — `VistaClient`
  with the typed error hierarchy (`VistaError` base, `VistaConfigError`,
  `VistaUpstreamError`, `VistaPermissionDenied`, `VistaNotFound`,
  `VistaFieldNotAvailable`, `VistaTimeout`).
- **Per-tenant field-set calibration** (`calibration.py`) — lazy probe
  routine that addresses the gap noted in `vista.md § 6`: the showcase
  adapter uses hardcoded constants; this MCP discovers each tenant's
  safe field set by candidate-then-drop probing on first real call,
  cached per process.
- **28 tools across 12 services** following the dotted naming convention
  per `KB § PATTERNS/mcp-tool-conventions.md`. The `access` column is the
  one to read before wiring a consumer — ✅ returns data today, 🔒 returns a
  typed 401 until Vista grants the per-method permission. Re-probed live
  (read-only) **2026-10-26/27** after Vista's "full access" grant on key
  `…644c`: nothing in the surface is gated any more, and a 401 on any ✅ row
  is a grant ROLLBACK. 🔴 = identity-PII family (LGPD — minimal projection by
  default, extra fields only when named in `fields`).

  | Tool | Vista route | Access | Notes |
  |---|---|---|---|
  | `vista.imoveis.list` | `/imoveis/listar` | ✅ | Paginated (≤50). 1,943 rows on `oneconsu`. Delta-syncable: `filter` on `DataAtualizacao`. |
  | `vista.imoveis.get` | `/imoveis/detalhes` | ✅ | `?imovel=` top-level. |
  | `vista.imoveis.list_filters` | `/imoveis/listarConteudo` | ✅ | Live enum values per field. |
  | `vista.imoveis.list_destaques` | `/imoveis/destaques` | ✅ *(2026-10-26)* | Featured listings `{Codigo, CodigoImovel}`; `pesquisa` required; no total. |
  | `vista.imoveis.list_finalidades` | `/imoveis/finalidades` | ✅ *(2026-10-26)* | `["Venda", "Aluguel"]`. |
  | `vista.imoveis.history` | `/imoveis/detalhes` → `prontuarios` relation | ✅ *(2026-10-26)* | Property history (CA2830 → 333 entries) — a field relation, not a route. Windowed client-side (`offset`/`limit`). `Texto` opt-in. |
  | `vista.usuarios.list` | `/usuarios/listar` | ✅ | 10 rows. Richest broker data (e-mail, Setor, photo). |
  | `vista.agencias.list` | `/agencias/listar` | ✅ | 1 row (`Codigo` 1 = the `Empresa` for pipes). |
  | `vista.clientes.list` | `/clientes/listar` | ✅ *(granted 2026-08-21)* | Paginated (≤50). **~44k rows**, no `DataAtualizacao` ⇒ no delta sync. LGPD: default returns Celular/DataNascimento/Sexo/EstadoCivil/Profissao; the tenant ALSO holds CPFCNPJ/RG/addresses/bank (catalog) — excluded from the default. |
  | `vista.clientes.get` | `/clientes/detalhes` | ✅ *(granted 2026-08-21)* | `?cliente=` top-level. LGPD as above. |
  | `vista.clientes.history` | `/clientes/detalhes` → `historicos` relation | ✅ *(2026-10-26)* | Client history. Vista silently omits the `Data` sub-field (Hora comes back). |
  | `vista.clientes.list_filters` | `/clientes/listarConteudo` | ✅ *(2026-10-26)* | Distinct values (Status, Interesse, VeiculoCaptacao…). |
  | `vista.corretores.list` | `/corretores/listar` | ✅ *(granted 2026-10-26)* | 24 brokers, `{items, meta}` envelope, top-level `page`/`limit`; rows are ONLY `{Codigo, Nome}` (Vista ignores `fields`). |
  | `vista.negocios.list` | `/negocios/listar` | ✅ *(2026-10-26)* | Top-level `codigo_pipe` XOR `codigo_cliente` (pipe 1 ~8.7k, pipe 2 ~2k). Paging via `pesquisa.paginacao` + `fields` (≤50). `valor_total` sibling. Client name opt-in. |
  | `vista.negocios.get` | `/negocios/detalhes` | ✅ *(2026-10-26)* | `?codigo_negocio=` top-level. |
  | `vista.pipes.list` | `/pipes/listar` | ✅ ⚠️ *(2026-10-26)* | Needs `pesquisa.filter.Empresa`. **Answers `[]` on this tenant** although pipes 1/2 hold deals — unsettled; use `CodigoPipe` from deals. |
  | `vista.agenda.list` | `/agenda/listar` | ✅ *(2026-10-26)* | ~3.9k activities; `filter`/`order`/paging (≤50). NomeCliente/Texto/Local opt-in. |
  | `vista.agenda.get` | `/agenda/detalhes` | ✅ *(2026-10-26)* | `?codigo=` top-level; body keyed by code (unwrapped). `TipoAtividade` is a 500 here. |
  | `vista.proprietarios.list` | `/proprietarios/listar` | ✅ 🔴 *(2026-10-26)* | ~8.5k owners. **Default `Codigo`+`Nome` only**; CPFCNPJ/RG/bank/income only when named in `fields`. |
  | `vista.proprietarios.get` | `/proprietarios/detalhes` | ✅ 🔴 *(2026-10-26)* | `?codigo=` top-level. Same LGPD default. |
  | `vista.contratos.list` | `/contratos/listar` | ✅ 🔴 *(2026-10-26)* | JSON list (few rows), UPPERCASE keys; Vista ignores projection/paging, so relation objects (Clientes/Proprietarios/…) + OBS are dropped CLIENT-SIDE by default. |
  | `vista.imoveis.add_photos` | `POST /imoveis/fotos` | ✍️ ✅ *(permitted 2026-10-26)* | Write. Photos by public URL, keyed map. Denied 2026-09-16 → permitted after the grant. |
  | `vista.leads.submit` | `POST /lead` | ✍️ ✅ | Write. `nome`+`mensagem`+`veiculo`+(`email`\|`fone`). Vista de-dups on existing clients. |
  | `vista.diagnostics.probe` | — | ✅ | 9-row baseline (incl. `/status`); read `unexpected`, not `status`. |
  | `vista.diagnostics.probe_write_permissions` | — | ✅ | Empty-POST write verdicts — non-mutating (Vista authorises before it validates). All three routes `permitted` since 2026-10-26. |
  | `vista.diagnostics.list_known_endpoints` | — | ✅ | Static catalog + `probe_status` (incl. write-only `/negocios/etapas`, `/contratos/detalhes`). |
  | `vista.diagnostics.show_calibrated_fields` | — | ✅ | Per-tenant safe field set. |
  | `vista.diagnostics.list_fields` | `/<family>/listarcampos` | ✅ *(2026-10-26)* | The tenant's REAL field catalog (imoveis 266 + 13 relations, clientes 91, usuarios, agencias, agenda). Read it before claiming a field/capability is absent. |

- **✍️ Write tools are OFF by default.** They mutate the agency's live CRM,
  so they return a typed `WritesDisabled` unless the server runs with
  `VISTA_MCP_ALLOW_WRITES=1`. There is deliberately no update/delete-photo
  tool — `/imoveis/fotos` accepts `DELETE` on live listings (`vista.md § 4.7`).
- **🔒 and ❌ are different answers, and the tools say which.** A gated tool
  returns `probe_status: "permission_gated"` with a typed 401 — meaning *ask
  Vista for the grant*, not *retry*, and not *this does not exist*. Routes
  that answer 404 (`/clientes/lead` — leads live at top-level `/lead` —, `/negociacoes/*`, and the ten other
  families in `vista.md § 4.6`) get **no tool at all**: a tool that can only
  ever report "no route" misrepresents the surface. See `vista.md § 4.2`.
  Before concluding something is absent, read `vista.diagnostics.list_fields`:
  on this tenant **history** (`prontuarios`, `historicos`) and **owner data**
  (`proprietarios`) are field relations, not routes.
- **Pydantic In/Out per tool** with `Field(description=...)` so MCP
  introspection surfaces help text automatically.
- **Hierarchical registration** — each leaf module exports `HANDLERS` +
  `tool_descriptors()`; `tools/__init__.py` aggregates; `server.py`
  registers once at startup.

## What this Phase 1 does NOT ship (deferred per PROJECT.md)

- Phase 5 — keeper detector for guide ↔ adapter drift.
- Write tooling beyond `add_photos` + `leads.submit` — `/clientes/anexos` is
  PERMITTED on our key since 2026-10-26 but nothing needs it; `/negocios/etapas`
  (PUT, stage moves) and `/contratos/detalhes` (POST/PUT) are write-only and
  unwrapped; photo update/delete is excluded on purpose.
- `/vendas` (exists, bare GET → 500, query shape unknown) and `/reloadcache`
  (Vista-side cache flush — side-effecting) have no tool.
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
- **Gated families calibrate lazily and stay un-armed until granted.**
  `get_cliente_fields` returns the floor `["Codigo"]` and — deliberately —
  does **not** cache a 401, so the first call after a grant runs a real
  calibration pass with no restart. **`clientes` was granted 2026-08-21** (11 of
  the candidates accepted — `vista.md § 4.2`). `corretores` is **no longer
  calibrated** (2026-10-27): since the 2026-10-26 grant the route ignores
  `fields` and always answers `Codigo` + `Nome`, so `show_calibrated_fields`
  leaves `corretores` empty by design.
  🔴 Candidate sets must stay generous **supersets** of NON-identity fields:
  calibration only ever narrows, so a field absent from a CANDIDATE_* list can
  never be discovered — but `CANDIDATE_CLIENTE_FIELDS` is also the default
  projection, so identity PII (CPFCNPJ, RG, addresses, bank) is kept out of it
  on purpose and pinned by a test. The real catalog is
  `vista.diagnostics.list_fields`.
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
│   ├── negocios.py    — deals (pipeline) — 2026-10-26
│   ├── pipes.py       — pipelines — 2026-10-26
│   ├── agenda.py      — activities/visits — 2026-10-26
│   ├── proprietarios.py — 🔴 owners (LGPD-minimal default) — 2026-10-26
│   ├── contratos.py   — 🔴 sale contracts (client-side projection) — 2026-10-26
│   ├── leads.py       — ✍️ vista.leads.submit
│   ├── _common.py     — shared client (+ DI seam) / typed_error / write gate / history window
│   └── diagnostics.py
├── tests/
│   ├── test_smoke.py  — import + registration smoke test
│   └── test_full_surface_tools.py — tool tests for the 2026-10-26 surface (Fake via DI seam)
└── README.md          — this file
```

**Not in this directory** — imported from the seed, never forked here:

- `VistaClient` + the 7-class error hierarchy + `extract_items` → `noctusai_lib.integrations.vista.client`
- `vista_*_to_showcase` normalizers → `noctusai_lib.integrations.vista.normalizers`
- `Showcase*` DTOs → `noctusai_lib.integrations.vista.types`
- `calibrator` + the CANDIDATE_* field sets → `noctusai_lib.integrations.vista.calibration`
- LGPD-minimal default projections (`DEFAULT_*_FIELDS`, `project_contrato`) → `noctusai_lib.integrations.vista.projections`

(`client.py` / `normalizers.py` lived here in the original Phase 1 layout; commit
`b3e0b10f` moved them to the seed as part of the shared `mcp/_kit` refactor.
`calibration.py` followed 2026-08-03 — P2.0a of the
`social-wiring-imoveis-vista-2026-08` roadmap — because a product-side Vista sync
needs the same per-tenant field set, and a calibrator reachable only from the MCP
host forces every backend consumer to hardcode a field list instead.)
