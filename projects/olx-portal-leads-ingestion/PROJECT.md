# Grupo OLX (ZAP / VivaReal / ImovelWeb) portal-lead ingestion — MCP map + full vertical slice

> **Status: BUILT, not merged, not deployed** (2026-08-17). All four slices are
> implemented on `feat/olx-portal-leads-mcp` — see `HANDOFF.md` beside this file
> for the commit list, the verification actually run, and the merge steps.
> Authored 2026-08-14; revised 2026-08-17 to make the MCP a hard prerequisite.
>
> **Gate 1 is still open and still blocks deploy.** It needs the real
> SECRET_KEY. The receiver is inert until then — an unconfigured secret 401s
> every delivery by design — so merging is safe, but calling the integration
> live is not. Waves 3–4 were built ahead of Gate 1 on explicit instruction to
> finish end-to-end; the contract they build on therefore remains UNVERIFIED
> until the gate passes, and correcting it afterwards is expected work, not a
> defect.

## Context

`products/social-wiring` today receives leads from exactly one automated
channel: **Meta Lead Ads**. Everything downstream of ingestion is already
source-generic — `leads.origem_id → lead_sources`, Portal ROI, the funil
trigger, analytics — and `lead_sources` already carries the canonical slugs
`zap`, `viva-real`, `imovel-web`, `olx`, `casa-mineira`. They are attribution
labels for spreadsheet-imported leads; **no portal has an ingestion path**.

The goal is to bring portal leads in automatically, starting with ZAP.

Research findings that shape the design (sources at the bottom):

1. **ZAP has no lead-pull API.** Grupo OLX pushes each lead as an individual
   `POST` + JSON to a URL you register with them. Auth is **HTTP Basic**,
   base64 of `vivareal:<SECRET_KEY>`; the key is **per CRM, not per client**.
   Delivery status is decided **only** by our HTTP status code — the response
   body is explicitly ignored. 3 retries, 14-day store-and-forward, duplicates
   expected ⇒ idempotency on `originLeadId` is mandatory, not optional.
2. **No sandbox exists.** The closest thing is their beta *endpoint validator*
   (URL + token + sample body → shows our status code), then a homologation
   form. So we ship our own emitter as the dev sandbox.
3. **One webhook carries every Grupo OLX portal** — ZAP, VivaReal, OLX and,
   once the client emails `atendimento@imovelweb.com.br` for an activation
   code, **ImovelWeb and Casa Mineira too**. Priority #2 is plausibly a config
   step on this same pipe rather than a second integration. Unconfirmed against
   live traffic; a direct-ImovelWeb adapter stays a fallback.
4. **The payload no longer names the portal** — `leadOrigin` is `"Grupo OLX"`
   (or `"MCMV_OLX"`), not `ZapImoveis`/`VivaReal` as older docs showed.
   Decision: attribute to a **new `grupo-olx` source**, keep the raw
   `leadOrigin`/`leadType` in `origem_raw`, and add a splitter later once real
   traffic shows what actually distinguishes the portals. No invented
   attribution into Portal ROI.

**Naming decision:** the MCP umbrella is `olx` (the vendor's real boundary),
not `zap` — one connector serves every Grupo OLX portal.

**Anti-fork rule for this build:** the payload contract is defined **once**, in
the seed, and imported by *both* the MCP server and the product receiver.
The MCP is a map over the same module the runtime uses, never a second copy.

**Sequencing rule — the MCP is a PREREQUISITE, not a parallel track.** Slices A
and B ship first, and the connector is **registered and actually callable**. It
is then pointed at the real Grupo OLX surface with the real key, and every
divergence between the vendor's prose and what the API really does is corrected
in the seed `contract.py` and recorded in the KB doc's change log. Only once
**Gate 1** (below) passes do slices C and D get dispatched, so the product
receiver is built against a *verified* contract. A doc-only contract is a guess
until something has called the API — building the product on one would mean
discovering the divergence in production, on leads that cannot be replayed
after 14 days.

---

## Slice A — seed: the contract, the parser, the adapter

### A1. New webhook scheme in the seed (named-seam extension, not a fork)

`seed/lib/backend/noctusai_lib/security/webhook_signatures.py` supports
`sha256_prefixed` / `sha256_hex` / `svix`. Grupo OLX uses a **Basic
shared-secret** scheme, so add a fourth:

- extend the `WebhookScheme` Literal + `_DEFAULT_SIGNATURE_HEADER`
  (`basic_shared_secret` → `Authorization`);
- `verify_basic_shared_secret(header_value, secret, *, expected_username="vivareal") -> bool`
  — strip `Basic `, base64-decode, split on `:`, `hmac.compare_digest` the
  second segment against the secret. Constant-time; malformed header ⇒ `False`,
  never an exception;
- add the branch in `webhook_endpoint`'s `dependency`. Everything else
  (`bypass_when_unset`, `ResolvedSecret.extras`, raw-body handoff) is reused
  as-is.

Tests alongside the existing ones in `seed/lib/backend/tests/security/`.

### A2. `seed/lib/backend/noctusai_lib/integrations/olx/`

Modelled on `noctusai_lib/integrations/meta/` (whose `leadgen_webhook.py` is
the pure zero-IO precedent) and `integrations/vista/` (the Protocol + Fake +
Real + factory shape). Ships the whole IO module — no half-shipped seed.

| Module | Contents |
|---|---|
| `types.py` | `OlxLead` frozen value object (`origin_lead_id`, `client_listing_id`, `origin_listing_id`, `name`, `email`, `ddd`, `phone`, `message`, `temperature`, `transaction_type`, `lead_type`, `timestamp`, `extra_data`, `raw`); `OLX_LEAD_TYPES` (`CLICK_SCHEDULE`, `CLICK_WHATSAPP`, `CONTACT_CHAT`, `CONTACT_FORM`, `PHONE_VIEW`, `VISIT_REQUEST`), `OLX_TEMPERATURES` (`Baixa`/`Média`/`Alta`), `OLX_TRANSACTION_TYPES` (`RENT`/`SELL`) |
| `contract.py` | **The single source of truth.** `OLX_LEAD_FIELDS` (name → type/required/notes), `OLX_LEAD_JSON_SCHEMA`, `validate_olx_lead_payload(payload) -> list[ContractViolation]`, `OLX_RESPONSE_SEMANTICS` (2xx ok / everything else retried), `OLX_RETRY_POLICY` (3 attempts, 14-day store), `OLX_SAMPLE_LEAD` |
| `webhook.py` | `parse_olx_lead_webhook(payload) -> OlxLead \| None` — pure, zero IO, zero FastAPI, `None` (never raises) on a malformed body, `raw` carried verbatim. `verify_olx_basic_secret` delegates to A1 |
| `normalizers.py` | `olx_lead_to_lead_payload(lead, *, origem_source_id, corretor_map=None) -> dict` — pure map onto the payload `leads_service.create_lead` expects; phone as `f"{ddd}{phone}"` when `phoneNumber` is absent; `data_entrada` from `timestamp` (raises `ValueError` when unparseable — never guesses, mirroring `map_meta_lead_to_lead_payload`) |
| `endpoints.py` | `OLX_ENDPOINT_BASELINE` — `(path, expected_bare_GET_status, probe_status, note)` rows, the single source for both MCP diagnostics tools |
| `protocol.py` / `fake.py` / `real.py` / `factory.py` | `OlxLeadManagerAdapter` for the **outbound** direction (`POST /v1/addLeads` on `crm-leadmanager-leadreceiver-api.olx.com.br`, headers `X-API-KEY` + `X-Agent-Name`) + `FakeOlxLeadManagerAdapter` + `get_olx_lead_manager_adapter(...)` factory. Rate limiting/retries via `noctusai_lib.integrations.rate_limit` |

Tests: `seed/lib/backend/tests/integrations/olx/` — parser (batch/malformed/MCMV
variants), contract validator, normalizer, Fake/Real/factory selection.

---

## Slice B — `mcp/olx/` (the in-house map)

Composes `mcp/_kit` (see `mcp/_kit/README.md`); **do not copy `mcp/vista`**.
Shape per `KB § CONTEXT/PATTERNS/architect/mcp-tool-conventions.md` — 3-segment
dotted names, Pydantic `In`/`Out` per tool.

```
mcp/olx/
  server.py          # bare sys.path insert → _kit bootstrap (prepare_sys_path pins the in-tree seed)
  settings.py        # frozen OlxSettings(ConnectorSettings) + make_get_settings
                     #   env_map: OLX_WEBHOOK_SECRET / OLX_API_KEY / OLX_AGENT_NAME / OLX_RECEIVER_URL
  api.py             # OlxApiError + 424 not-configured gate → _kit.transport.request_json
  types.py           # Pydantic In/Out
  tools/{leads,webhook,diagnostics}.py
  tests/test_smoke.py
  README.md
  .env               # gitignored, connector-owned
```

| Tool | Kind | Job |
|---|---|---|
| `olx.webhook.describe_contract` | READ, zero-IO | Returns `OLX_LEAD_FIELDS` + JSON Schema + response semantics + retry policy **straight from the seed `contract.py`** — the machine-readable map |
| `olx.webhook.validate_payload` | READ, zero-IO | Runs `validate_olx_lead_payload` over a supplied dict → typed violations. What in-house code and captured live bodies get checked against |
| `olx.webhook.simulate` | WRITE 🔒 | POSTs a synthetic lead (selectable `lead_type` / `temperature` / `transaction_type`) at our own receiver URL with the Basic header — **our substitute for the missing sandbox**, mirroring their validator |
| `olx.leads.push` | WRITE 🔒 | `POST /v1/addLeads` (Gestor de Leads, outbound) via the seed adapter |
| `olx.diagnostics.connection_status` | READ, no API call | `{ok, configured, receiver_url, has_webhook_secret, has_api_key, homologation_state, next_step}` |
| `olx.diagnostics.probe` | READ | Walks `OLX_ENDPOINT_BASELINE`; reports `unexpected` rather than raw status (a documented 401/405 is not a fault) |
| `olx.diagnostics.list_known_endpoints` | READ | Static catalog derived from the same baseline + the wrapping tool per path |
| `olx.webhook.record_delivery` | WRITE 🔒 | Persists one **real** inbound body (pasted, or read from the receiver's `olx_lead_events`) into `mcp/olx/fixtures/observed/<origin_lead_id>.json`, secret-free. The corpus every later assertion is made against |
| `olx.contract.diff_observed` | READ, zero-IO | Diffs the recorded corpus against `contract.py` → fields present live but undocumented, documented but never seen, type/enum mismatches, and required-fields that arrived null. **This is the tool that closes the doc-vs-reality loop** and its output is what gets written into the KB change log |

Both write tools carry the house `confirm: bool = False` gate — `confirm != True`
⇒ typed error `status=412`, **no side effect** (`_kit.errors.confirmation_required_message`).
Never log or echo the secret; redact at the boundary (`redact_api_key` precedent).

Docs (same commit): `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/olx.md` authored
against the structure of `INTEGRATIONS/vista.md` (auth · envelope · endpoint
inventory with the status legend · adapter contract · MCP design notes · change
log with live-probe dates), `KNOWLEDGE-BASE/MCP-SERVERS/olx.md` + the README
row, and `KB § INDEX.md`.

**`.mcp.json` registration — corrected 2026-08-17 against the tree.** The file
is **gitignored** (per-machine, absolute `cwd`), so the row cannot ship in a
commit. The canonical row is documented in `KNOWLEDGE-BASE/MCP-SERVERS/olx.md`:

```json
"olx": {
  "command": "mcp/noctusai/.venv/bin/python",
  "args": ["mcp/olx/server.py"],
  "cwd": "<repo root>"
}
```

Register it **after this branch merges into `dev`**, not before: `cwd` points at
the primary checkout, whose editable `noctusai_lib` has no `integrations.olx`
until the merge lands, so a row added early loads a server that ImportErrors at
every session start. Until then the connector is driven straight from its
worktree over stdio (`python mcp/olx/server.py`) — which is how the tool surface
was verified. Adding it to the session keep-list stays the user's call
(`CLAUDE.md §1` context-budget rule).

---

## Slice C — `products/social-wiring` backend

### C1. Migration `051_olx_portal_leads.sql`

Forward-only, idempotent, RLS two-policy pattern on every new table
(`*_select_own_org` + `*_service_role`), exactly as `044_meta_webhook_events.sql`.

- **`olx_lead_events`** — raw delivery inbox, PK `origin_lead_id TEXT`,
  `org_id` nullable (NULL ⇒ `unresolved`), `payload JSONB`,
  `status CHECK IN (received, processed, error, unresolved, ignored)`,
  `error`, `attempts`, `received_at`, `processed_at`. Mirrors `meta_webhook_events`.
- **`olx_leads`** — lossless ledger, PK `origin_lead_id TEXT`, typed core
  (`name`/`email`/`phone`/`client_listing_id`/`transaction_type`/`temperature`/
  `lead_type`/`timestamp`) + `extra_data JSONB` + `raw JSONB`. Mirrors `meta_ads_leads`.
- **Generic idempotency on `leads`** (replaces the per-portal-column trap):
  `external_source TEXT` + `external_lead_id TEXT` + partial unique
  `uq_sw_leads_org_external_lead (org_id, external_source, external_lead_id)
  WHERE external_lead_id IS NOT NULL`. Backfill the existing Meta rows
  (`external_source='meta-lead-ads'`, `external_lead_id=meta_lead_id`);
  `meta_lead_id` and `uq_sw_leads_org_meta_lead_id` are left untouched —
  additive, no destructive change.
- Extend the `integration_accounts.provider` CHECK with `'olx'`.

`lead_sources` is **not** migration-seeded (org-scoped): add
`{"slug": "grupo-olx", "label": "Grupo OLX (ZAP/VivaReal)", "categoria": "portal", ...}`
appended at `ordem: 24` in `app/modules/leads/seed_data.py::CANONICAL_SOURCES`
— appended, never interleaved, so no consumer's legend order shifts (same
rationale the `meta-lead-ads` entry records).

### C2. New module `app/modules/portal_leads/`

Mirrors `app/modules/meta_ads/` — **persist-then-200-then-process**, which is
the only correct shape here given OLX judges us purely on the status code.

- `routers/olx_webhook.py` — `POST /api/portals/olx/leads`. Public, rate-limited,
  guarded by `webhook_endpoint(scheme="basic_shared_secret", bypass_when_unset=False,
  secret_resolver=_resolve_olx_secret)`. Resolver reads the secret **per request**
  (never captured at import). Handler: record the event → return 200 →
  process in a Starlette `background=` task (note the SlowAPI/`functools.wraps`
  annotation trap documented at `meta_ads/routers/leadgen_router.py:245-252`).
  Returns 4xx **only** for a missing `clientListingId` on a listing lead, which
  the docs say triggers reprocessing.
- `services/olx_webhook_service.py` — `OlxWebhookService` with keyword DI
  collaborator seams (`dedup`, `org_resolver`, `ingest_fn`, `publisher`), the
  same 3-layer dedup as Meta (Redis SETNX → `olx_lead_events` PK →
  `olx_leads` PK), `MAX_ATTEMPTS = 5`, `drain_pending(limit=100)`.
- **Org resolution chain** (never guess — park as `unresolved` instead):
  1. path-scoped org token if OLX registers a per-advertiser URL for us;
  2. `clientListingId → imoveis.codigo → org_id` (migration `040_imoveis.sql`);
  3. configured single org (`OLX_LEADS_ORG_ID`, mirroring `META_ADS_ORG_ID`);
  4. else `status='unresolved'`, no write. This is the tenant-leak guard.
- `services/olx_ingest_service.py` — thin: calls the seed's
  `olx_lead_to_lead_payload` then `leads_service.create_lead`; idempotent
  read-then-write on `(org_id, 'grupo-olx', origin_lead_id)`; plus a paged
  `backfill_olx_leads` (page size 500 — `MockSupabaseClient.range()` is a no-op,
  so an unpaginated select tests green and truncates live; this is the
  `98377d26` bug class).
- Register in `app/main.py` **before** `leads.router`'s catch-all `/{lead_id}`.
- Scheduler job `olx_leads_retry`, cron `*/15 * * * *` → `drain_pending()`,
  added in `app/modules/meta_ads/scheduler.py`'s `configure()` (or a peer
  module if the engineer prefers not to widen that file).

### C3. Config + credentials

The SECRET_KEY is **per CRM**, so it belongs in the app-wide, service-role-only
`app_integration_config` — *not* per-org `integration_accounts`. Add to
`app/services/app_config_store.py`, DB-first with env fallback, alongside the
`META_*` keys: `OLX_WEBHOOK_SECRET_KEY`, `OLX_LEADS_ORG_ID_KEY`,
`OLX_LEADMANAGER_API_KEY`, `OLX_LEADMANAGER_AGENT_NAME_KEY`, plus a
`resolve_olx_config()` resolver. Env names mirror in `app/config.py`.

Add the `olx` entry to `app/services/integration_providers.py::PROVIDERS`
(`manual_entry=True`, `manual_key_fields` = secret key / API key / agent name)
— the file's own "Extension recipe" docstring is the contract.

---

## Slice D — frontend

Contract-first: builds against the endpoints declared in C2, in parallel with C.

- `frontend/src/hooks/useOlxLeads.ts` (+ `.test.ts`) — TanStack Query over
  `/api/portals/olx/*`. **Gate loading on `isPending || isFetching`, never
  `isLoading`** (`check_lying_loading_state`).
- `frontend/src/pages/leads/components/OlxWebhookCard.tsx` (+ test) — modelled
  on `pages/meta/LeadgenWebhookCard.tsx`: receiver URL to copy into the OLX
  homologation form, secret status, last-delivery health, unresolved-event
  count. Mounted in `pages/leads/Configuracao.tsx`.
- Complete loading / empty / error / success states. `Origens.tsx` needs no
  change — it is already source-generic and will show `grupo-olx` once the
  dimension is provisioned.

---

## Execution

Self-branch off `origin/dev` (never work on `dev`). **MCP-first**: the connector
is built, registered and validated against the real API before a single line of
product code is written.

| Wave | Slices | Agent |
|---|---|---|
| 1 | **A** (seed contract + parser + normalizer + adapter + webhook scheme) | `backend-engineer` |
| 2 | **B** (`mcp/olx` + KB docs; `.mcp.json` row post-merge) | `backend-engineer` |
| — | **🚦 Gate 1 — live validation.** Blocks waves 3–4. See below. | tech-lead + user (key) |
| 3 | **C** (product backend), **D** (frontend) — parallel, file-disjoint | `backend-engineer` + `frontend-engineer` |
| 4 | integration on the merged tip, gates, docs sync | tech-lead |

A and B are sequential (B imports A's `contract.py` / `endpoints.py`). C and D
are parallel and build against the **post-Gate-1** contract plus the endpoint
shapes declared above. Re-run the gates on the **merged tip**, not per-branch —
derived artifacts couple the slices.

### 🚦 Gate 1 — live validation (the reason the MCP comes first)

Needs the real SECRET_KEY (and the Gestor de Leads `X-API-KEY` / `X-Agent-Name`
if we also want the outbound direction). Nothing in wave 3 starts until every
line here is green or explicitly waived in writing.

1. `olx.diagnostics.connection_status` answers from a live session — proves the
   connector is registered, loaded, and reading its `.env`.
2. `olx.diagnostics.probe` runs against the real hosts. Every row is either
   `as_expected` or lands in `unexpected` **and gets its baseline row corrected**
   in `endpoints.py`. A guessed expected-status is worse than none — it trains
   us to ignore the report.
3. `olx.leads.push confirm=true` against `/v1/addLeads` with the real key
   returns 200 (or a typed, *understood* rejection). This is the only
   authenticated live call the vendor exposes to us, so it is the only proof the
   credentials and the base URL are right.
4. At least one **real** inbound delivery is captured via
   `olx.webhook.record_delivery` — from their beta endpoint validator pointed at
   a temporary public receiver, or from the first homologation traffic.
5. `olx.contract.diff_observed` reports **zero unexplained divergence**. Any
   divergence is fixed in the seed `contract.py` first, and both the fix and the
   observation date go into `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/olx.md`'s change
   log. Specifically resolve, with evidence rather than inference:
   - does `leadOrigin` ever carry the portal name, or is it always `Grupo OLX`?
     (decides whether the `grupo-olx` splitter is buildable at all)
   - is the Basic username literally `vivareal`, or has it been rebranded?
   - which `extraData` keys actually arrive, and for which `leadType`s?
   - do ImovelWeb leads land on this pipe once activated, and how are they marked?
6. The KB doc is rewritten from **observed** behaviour, with the doc-only rows
   explicitly labelled as such (vista.md's `✅ live-200 / 🔒 live-401 / ❌ live-404
   / 📖 doc-only / ❓ referenced` legend). That rewritten doc — not the vendor's
   HTML — is the brief wave 3 is dispatched with.

## Verification

```bash
# seed
cd seed/lib/backend && python -m pytest tests/integrations/olx tests/security -q
# MCP
cd mcp && python -m pytest olx/tests -q && python -m pytest _kit/tests -q
# product backend — full suite, 1897 passing is the baseline
cd products/social-wiring/backend && python -m pytest -q
# frontend
cd products/social-wiring/frontend && npm test && npm run build
# methodology gates (pre-commit runs these; run them early)
python mcp/noctusai/cli.py --verify-kb-sync
python mcp/noctusai/cli.py --check-claude-md-router
```

Auth-boundary tests must assert strict `== 401` (never `in (401, 404)`), and
must enumerate that `POST /api/portals/olx/leads` is *intentionally* public —
the same shape as `tests/modules/meta_ads/test_leadgen_auth_boundary.py`.

End-to-end, no live key required:

1. Run the social-wiring backend locally; set the OLX webhook secret.
2. `olx.diagnostics.connection_status` → expect `configured: true`.
3. `olx.webhook.simulate confirm=true` at the local receiver → expect **200**,
   one row in `olx_lead_events` (`status='processed'`), one in `olx_leads`,
   one in `leads` with `origem_id → grupo-olx`.
4. Re-run the same `originLeadId` → still 200, **no** second `leads` row
   (this is the duplicate-delivery contract).
5. Wrong secret → **401**. Missing `clientListingId` on a listing lead → **4xx**.
6. `olx.webhook.validate_payload` against a captured body → zero violations.

Once the key and a public URL exist: point Grupo OLX's beta endpoint
validator (`developers.grupozap.com/webhooks/endpoint_validator/`) at the
deployed receiver, then submit the homologation form. `olx.diagnostics.probe`
re-runs then, and the observed statuses get written into the change log of
`KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/olx.md`.

## Open items to confirm against live traffic (tracked in the KB doc, not guessed)

- Whether ImovelWeb / Casa Mineira leads really arrive on this same webhook
  once activated, and what distinguishes them in the payload. If they do →
  priority #2 is a config step + a splitter. If not → a direct ImovelWeb
  adapter reusing Slice A's shape.
- Whether OLX registers one endpoint per CRM or per advertiser — decides
  whether org resolution step 1 or step 2 is the primary path.
- Whether `clientListingId` values match our `imoveis.codigo` for this client.

## Sources

- [Integração Leads — Grupo OLX](https://developers.grupozap.com/webhooks/integration_leads.html)
- [Webhooks — Segurança](https://developers.grupozap.com/webhooks/security.html)
- [Endpoint validator (beta)](https://developers.grupozap.com/webhooks/endpoint_validator/)
- [Gestor de Leads — API](https://developers.grupozap.com/leadManager/api_lead_integration.html)
- [Gestor de Leads — ImovelWeb e Casa Mineira](https://developers.grupozap.com/leadManager/imovelweb_casamineira.html)
- [olxbr/crm-lead-integration (reference samples)](https://github.com/olxbr/crm-lead-integration)
