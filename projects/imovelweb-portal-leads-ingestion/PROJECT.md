# ImovelWeb portal-leads ingestion (OpenNavent) — Project Document

> **This is a living document, not a rigid checklist.** Revise phases, fold in
> optimizations, update the Change Log as you learn.
>
> **Phases A and B have shipped** (seed package + MCP connector, on
> `feat/imovelweb-portal-leads`, unmerged). Everything from Gate 1 onwards is
> blocked on sandbox credentials, which is a user action, not an engineering one.

- **Created:** 2026-08-17
- **Last updated:** 2026-08-18
- **Status:** ⏳ A ✅ · B ✅ · C ✅ · D ✅ · Gate 0 ran (partial, by design) · **EVERYTHING BUILDABLE WITHOUT CREDENTIALS IS BUILT.** The only open input is Gate 1: sandbox credentials from `integracao@imovelweb.com.br`. The draft email is at `gate-1-credential-request.md` and carries one user decision (ReadOnly vs Read-and-Write). Nothing is live: the receiver 401s every delivery until a secret is configured, and the migration is a file that has not been applied.
- **Owner / stakeholders:** jraphaelsst · tech-lead orchestrator
- **Related docs:** `KB § INTEGRATIONS/imovelweb.md` (the vendor contract) · `KB § MCP-SERVERS/imovelweb.md` · `KB § INTEGRATIONS/olx.md` (the sibling pipe) · `projects/olx-portal-leads-ingestion/PROJECT.md` + `HANDOFF.md` (the template this mirrors) · `KB § PATTERNS/security/webhook-signatures.md` · `KB § PATTERNS/backend/seed-fake-real-adapter.md` · `KB § PATTERNS/security/lgpd.md` · `KB § PATTERNS/backend/database-rls.md` · `KB § PATTERNS/backend/di-test-seam.md`
- **Project slug:** `imovelweb-portal-leads-ingestion` at `projects/` — cross-cutting (seed package + MCP connector + product slice), named for symmetry with `olx-portal-leads-ingestion`.

---

## 1. Context & Purpose

`products/social-wiring` owns inbound leads. A sibling agent has just built
**Grupo OLX portal-leads ingestion** on the unmerged branch
`feat/olx-portal-leads-mcp`, establishing the shape this project reuses: a
`portal_leads` module named for the **category** so a second portal lands beside
`olx_*`; a generic idempotency pair (`leads.external_source` +
`leads.external_lead_id`); a two-table inbox+ledger per vendor; and an MCP
connector used as a contract-validation gate *before* product code is trusted.

Priority #2 is **ImovelWeb**. The OLX project left an open question — *"do
ImovelWeb leads land on this pipe?"* — and hypothesised they might, once the
advertiser emails `atendimento@imovelweb.com.br` for an activation code.

**The research answer is: partly, and lossily.**

1. **ImovelWeb is not a Grupo OLX property.** It is a **Navent** brand;
   QuintoAndar acquired Navent's real-estate operations in 2022. Its developer
   platform is *Open / OpenNavent*, branded Grupo QuintoAndar, with its own
   public API, its own sandbox, and its own callback system.
2. **The Grupo OLX bridge is real but lossy.** Gestor de Leads does ship a
   first-party ImovelWeb / Casa Mineira bridge. But leads then arrive stamped
   `leadOrigin: "Grupo OLX"`, which names no portal — so attribution,
   enrichment and reconciliation are all lost.

Today an imobiliária's ImovelWeb enquiries either never reach the CRM, or reach
it as unattributable spreadsheet imports. The win: a seeker signals on
ImovelWeb, and within seconds the lead is in `leads` with the right `origem`, the
right org, the buyer-intent profile attached, and a reconciliation job standing
behind it so a missed delivery is recovered rather than lost.

**Why direct rather than the bridge** (user decision, §2): the direct path names
the portal in the payload, resolves the tenant off a code *we* assign, exposes a
pull API for reconciliation and enrichment, and — uniquely — ships a **sandbox
event simulator**. That last one closes the exact gate the OLX project could not:
we can prove the contract before a single real lead exists.

---

## 2. Confirmed constraints

- **Ingestion path — direct OpenNavent API, not the Grupo OLX bridge.** *(Rules out a config-only stopgap. Costs a real build; buys per-portal attribution, tenant resolution off a code we choose, reconciliation and enrichment.)*
- **Branch base — stack on `feat/olx-portal-leads-mcp`, not `origin/dev`.** *(Six hard dependencies exist only on that branch — §8. The sibling agent is still active there; conflicts get resolved at merge time by whoever merges. Branching from `dev` would force duplicating all six, including a second `leads.external_source` migration.)*
- **MCP connector is a prerequisite gate, not a follow-up.** *(`mcp/imovelweb` is built and validated against sandbox before the product code is trusted. The OLX project made the same call with far weaker justification — no sandbox, one authenticated endpoint.)*
- **Scope is all four legs** — lead events · reconciliation/backfill · smartlead enrichment · listing events (`AVISO_*`). *(See the `AVISO_*` gate in §7 Q1 — it is not purely an engineering call.)*
- **Touch only our own tree.** *(User, 2026-08-17: "dont touch work that is not yours. We got other agents working in parallel and the last to finish its job will deal with merging branches." Rules out editing `integrations/olx/`, `vista/client.py`, `mcp/olx/`, `migrations/051_*.sql`, `KB § INTEGRATIONS/olx.md` or the OLX project docs from this branch. Findings against them are **recorded and handed off** — §6 Phase A0 — never applied here. It also rules out us doing the merge: whoever finishes last does.)*
- **Shell first, dynamicize on demand.** *(User: "so we build a shell, then we dinamicize that shell if we need to propagate that." Build the ImovelWeb package concretely; generalize only when a second consumer actually needs it. This is the user's own framing of the §5.10 T3 verdict — fork now, lift at the named trigger — and it extends to T1/T2: local helpers first, seed lift once the OLX branch lands.)*
- **LGPD posture confirmed.** *(User: "about the LGPD matter, that's the right fit." The CPF is not stored in a typed column, not projected into `leads`, never returned, never logged — §5.2 and §10.)*
- **RLS hardening is deferred until after integration validation.** *(User: "After we validate integrations i'll decide on RLS policies for more robustness on safety matters." Ship the baseline two-policy shape — `_select_own_org` + the literal `service_role_bypass` — and do not invent stricter policies ahead of that decision. Revisit after Gate 2.)*
- **This session is design + seed shell.** *(No product wiring, no migration applied.)*
- **User confirmed the plan before any code.** *(Approved 2026-08-17 via plan mode; the decisions above are the user's, quoted from the answers, not inferred.)*

---

## 3. Design principles

1. **The 1.5-second response budget is the architecture, not a comment.** Every
   handler decision derives from it. Measure it (`RESPONSE_BUDGET_SECONDS = 1.0`,
   two-thirds of the vendor's ceiling), log overruns, and test it as a
   *round-trip count*, not a wall-clock assertion.
2. **Reconciliation is the durability guarantee — the webhook is only the fast
   path.** Unlike OLX, a missed delivery is recoverable. Say so in the module
   docstring; it is the single fact that makes the tight budget survivable.
3. **Never guess a tenant, never guess an attribution, never guess a date.** Park
   as `unresolved` rather than resolve wrongly; fall back to `imovel-web` rather
   than mint a slug for an unobserved `leadOrigin`; raise rather than invent a
   `data_entrada`.
4. **Separate the pipe from the portal.** `external_source` is the constant
   `imovelweb` (half of the unique index); `origem_id` is the per-portal
   `lead_sources` row. OLX conflated them because it had to; here that would be a
   duplication bug.
5. **Transcribed ≠ verified.** Every `FieldSpec.verified` is `False` and every
   endpoint-baseline expected status is `None` until an *observation* flips it —
   never a re-reading of the vendor's HTML. A guessed expectation makes the probe
   print `as_expected` for a number we invented, and an operator who learns the
   report lies stops reading it.
6. **The body is a hint, not truth.** There is no signature. Idempotency on
   `eventId` is the compensation; `GET /v1/mensagens/{id}` is the escalation, in
   the background, never in the request path.
7. **🔴 No model call anywhere in the delivery path — an LLM outage must never
   cost a lead.** *(User, 2026-08-17: "we must be really careful here to dont let
   any model's outage affect our app.")* Concretely, and these are testable
   invariants, not aspirations:
   - **The receiver imports no LLM client.** Not `noctusai_lib.integrations.llm`,
     not an embedding call, not a classifier. The vendor gives us 1.5 seconds; a
     model call cannot fit, and a model *outage* inside that window converts a
     provider incident into lost customer enquiries. A keeper-style import
     assertion in the receiver's test file pins this.
   - **Enrichment is downstream of durability, never upstream.** The order is
     always: verify → persist to `imovelweb_lead_events` → answer 2xx → resolve
     org → write the ledger → project into `leads` → *then* enrich. Every step
     after the durable write is independently retryable from the inbox, so an
     outage in any of them delays a lead rather than dropping it.
   - **Enrichment failures are degradations, not errors.** `smartlead` is a
     nullable column for this reason. If the enrichment call fails — vendor
     down, model down, quota exhausted — the lead is already in `leads` and
     working. Never mark the event `error` for a failed enrichment; never block
     the projection on it.
   - **If lead scoring is ever added, it is a separate job reading the ledger**,
     with its own retry and its own failure surface — never a step in ingestion.
     LGPD Art. 20 also engages there (§10.5), so the separation is doubly
     motivated.
   - **The same rule applies to our own tooling.** `mcp/imovelweb`'s zero-IO
     contract tools must keep working with no credentials and no network, which
     is what makes the connector usable for diagnosis *during* an outage rather
     than another thing that is down.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** **YES.** The OpenNavent
   payload, auth and callback semantics are vendor-level facts. Nothing about
   them is social-wiring-specific.
2. **Is the data source product-specific?** **NO** for the vendor client;
   **YES** for the org-resolution and lead-projection layer, which is bound to
   `social_wiring.leads` / `imoveis`.
3. **Is the placement product-specific?** **YES** — the receiver, the tables and
   the config card belong to `social-wiring`, the product that owns inbound
   leads.
4. **Is the visibility / permission rule the same?** **YES** — RLS
   `org_id = public.current_org_id()` + the literal `service_role_bypass`, same
   as every other lead surface.
5. **Does the seam already exist in seed?** **PARTLY.**
   `noctusai_lib.security.webhook_signatures.basic_shared_secret` exists (on the
   OLX branch) and is reused verbatim; `noctusai_lib.integrations.rate_limit` and
   `integrations.persistence.iter_paged_rows` exist. **New seam needed:**
   `noctusai_lib/integrations/imovelweb/` (the vendor package) and a
   client-credentials token module inside it.
6. **Default-on or opt-in?** **OPT-IN.** The receiver is inert until configured —
   no secret ⇒ 401 on every delivery, by design. That is what makes merging
   before Gate 2 safe.

**Litmus — per-product code count:** *a small section.* The vendor package,
contract, parser, normalizers and adapter are **0 lines per product** (pure seed).
The receiver, services, migration and config card are a single product-bounded
section in `social-wiring`, which is correct: it is the product that owns leads.

**Phase plan implications:** §6 phases work in **seed first, then one product** —
never product-by-product. There is no replication framing here and there must not
be one; a second consumer of ImovelWeb leads would consume the seed package, not
copy the receiver.

---

## 4. Scope

**In scope**
- Inbound `CONTACTO` + `CONTACTO_MENSAJE` callbacks → durable inbox → lossless
  ledger → unified `leads` projection.
- Self-serve callback registration: URL, auth header, language, event
  subscribe/unsubscribe, read-back diff.
- OAuth2 client-credentials auth with token caching, single-flight refresh and
  three-secret redaction.
- Scheduled reconciliation (hourly, 7-day lookback) + a manual backfill route.
- Smartlead / questionnaire enrichment, fetched in the background.
- Agency onboarding via the vendor's login button, and the `imovelweb_agencies`
  org-resolution map.
- `mcp/imovelweb` connector (~16 tools) as the Gate instrument.
- Frontend config + health card with the callback-registration panel.
- The three §6-Phase-A0 corrections to the OLX artifacts.

**Out of scope (for now — with reason)**
- **Listing events (`AVISO_ACTIVIDAD` / `AVISO_ESTADO_PUBLICACION` /
  `AVISO_CALIDAD`) and `CREDITO`** — *specified but gated.* The vendor delivers
  them only to **Read-and-Write** integrations, which also grants us
  publish/unpublish on ImovelWeb — a materially larger blast radius that overlaps
  `products/erp-imobiliario`'s outbound XML-feed surface. §7 Q1; the user decides
  at credential-request time, not the engineer.
- **A shared `portal_lead` normalization primitive across OLX + ImovelWeb** —
  N=2, forked with a named trigger. See §5 T3.
- **Outbound listing publication to ImovelWeb** — a different direction and a
  different product (`erp-imobiliario` already generates portal XML feeds).
- **Cross-pipe deduplication against Gestor de Leads** — advisory count only.
  §5 and §7 Q3.
- **A `wimoveis` `lead_sources` slug** — no observed BR traffic. §7 Q6.

---

## 4a. Dispatch routing

### 4a.1 Slice → Lens table

| Slice / Phase | Lens | Files (or globs) | Time-box | Dispatched as |
|---|---|---|---|---|
| **A0** OLX corrections + DRY lifts | architect-inline | `KB § INTEGRATIONS/olx.md`, `integrations/olx/{__init__,types,endpoints}.py`, `integrations/{endpoint_status,redaction}.py`, `integrations/vista/client.py`, `migrations/051_*.sql`, `mcp/olx/server.py`, `KB § MCP-SERVERS/*` | 2h | inline-empersonation |
| **A** Seed package | backend-engineer | `seed/lib/backend/noctusai_lib/integrations/imovelweb/**`, `seed/lib/backend/tests/integrations/imovelweb/**` | 6h | Agent dispatch |
| **B** MCP connector + KB ops doc | backend-engineer | `mcp/imovelweb/**`, `KB § MCP-SERVERS/imovelweb.md`, `KB § MCP-SERVERS/README.md` | 4h | Agent dispatch |
| **Gate 0** Spec-only verification | architect-inline | none (read-only probes) | 1h | inline-empersonation |
| **Gate 1** Sandbox verification | backend-engineer | `integrations/imovelweb/{contract,endpoints}.py`, `mcp/imovelweb/fixtures/observed/**` | 3h | Agent dispatch |
| **C** Product slice | backend-engineer | `products/social-wiring/backend/app/modules/portal_leads/{routers,services}/imovelweb_*`, `scheduler.py`, `app/config.py`, `app/services/{app_config_store,integration_providers}.py`, `migrations/0NN_imovelweb_portal_leads.sql`, `backend/tests/modules/portal_leads/test_imovelweb_*` | 8h | Agent dispatch |
| **D** Frontend slice | frontend-engineer | `products/social-wiring/frontend/src/hooks/useImovelWebLeads.*`, `src/pages/leads/components/ImovelWebWebhookCard.*`, `src/pages/leads/Configuracao.tsx` | 4h | Agent dispatch (parallel with C — file-disjoint) |
| **Security review** | security-advisor | the C diff | 1h | advisor consult |
| **Gate 2** Production verification | tech-lead | `contract.py` verified flags, `KB § INTEGRATIONS/imovelweb.md` §8 | — | tech-lead |

**C and D are file-disjoint and run in parallel.** Their contract is authored
once, here in §5, per `noc-contract-first` — neither side invents it.

### 4a.2 Codification expectations per slice

| Slice | s1 detected | s2 to memory | s3 KB+CLAUDE.md | s4 keeper | Why |
|---|---|---|---|---|---|
| A0 | yes | yes | yes | no | Two N≥3 lifts (endpoint-status vocabulary, secret redaction) — the code itself set the trigger. `check_admin_endpoint_service_role_bypass` already exists; 051's policy names simply need to conform |
| A | yes | yes | no | no | Language-parameterized contract is novel; too early to lift at N=1 |
| B | yes | no | no | no | `mcp/_kit` composition is already codified |
| C | yes | yes | **yes** | **maybe** | The 1.5 s response-budget discipline (persist-once-then-answer, round-trip-count testing) is a reusable receiver pattern the moment a third vendor has a tight SLA. `MockRequestBuilder.upsert()` being a silent no-op is a **test-lies** class — a strong `s4` candidate |
| D | yes | no | no | no | `isPending \|\| isFetching` is already keeper-gated |

### 4a.3 Routes-not-taken (pre-rejected by tech-lead)

| Route | Why rejected |
|---|---|
| Ride the Grupo OLX Gestor de Leads bridge instead of building direct | Leads arrive as `leadOrigin: "Grupo OLX"` — no portal attribution, no enrichment, no reconciliation, no sandbox. User decision, §2 |
| A shared `portal_lead` base class across OLX + ImovelWeb | N=2, and the six semantic differences land exactly where the abstraction would need parameters — §5 T3 |
| A sixth `WebhookScheme` (`static_token`) for the inbound header | We choose the header value, so `basic_shared_secret` fits with a different `basic_username`. Adding a scheme at N=1 widens the security surface for no gain. Fallback documented, not built (§5) |
| An `imovelweb_lead_id` column on `leads` | 041 did it for Meta, 051 replaced it with the generic pair. A third makes it a pattern |
| A new `imovel-web` lead-source slug | Already exists in `app/modules/leads/seed_data.py:68` with five alias rows |
| Re-fetch by `messageId` inside the request handler | An upstream round-trip inside a 1.5 s budget. Background only, behind `imovelweb_verify_by_refetch` |
| `noctusai_lib.security.oauth` as the home for the token module | That is the authorization-code / user-consent dance. This is machine-to-machine client credentials: no user, no redirect, no per-org consent |
| Fuzzy cross-pipe dedup key | Would silently merge two real people who share a phone. Advisory count only |

### 4a.4 Notes — surface + delivery

Standard: every slice files a delivery note; a surface note BLOCKS. Filed to
`projects/imovelweb-portal-leads-ingestion/proposals/`.

**Slice-specific surface triggers** — file a surface note and STOP if:
- Gate 0.4 shows the chosen language lacks the agency code *and* rung 2 of the
  resolution chain is also unavailable (no `imoveis` association).
- Gate 1.9 measures p99 pre-response latency above 1.5 s — the handler shape is
  wrong and §5's design must change before Phase C is trusted.
- Gate 0.6 shows `Mensaje.id` / `idMensaje` occupy a different id space from
  `eventId` / `messageId` — the reconcile dedup key needs a documented composite,
  and getting it wrong duplicates every lead.
- The vendor rejects our chosen `authorizationHeaderValue` at Gate 1.5 — the
  `static_token` fallback becomes live work.

---

## 5. Architecture / Data Model

The vendor contract lives in `KB § INTEGRATIONS/imovelweb.md` and, canonically,
in `contract.py`. This section covers **our** shapes only.

### 5.1 Seed package — `seed/lib/backend/noctusai_lib/integrations/imovelweb/`

Package named `imovelweb`, not `navent`: it matches the existing `lead_sources`
slug and is the boundary an operator recognises. The module header records that
the host is Navent's and the same package reaches AR/LatAm via a region
parameter.

| Module | Kind | Contents |
|---|---|---|
| `__init__.py` | — | Curated `__all__` façade. Docstring: both directions, the 1.5 s / 72 h contract, the UNVERIFIED marker |
| `types.py` | **PURE** | `ImovelWebLead` + `CallbackConfig` frozen dataclasses; `IMOVELWEB_EVENT_TYPES`; `IMOVELWEB_LEAD_EVENT_TYPES`; `IMOVELWEB_CONTACT_TYPES`; `IMOVELWEB_LEAD_ORIGINS`; `IMOVELWEB_CALLBACK_LANGUAGES` |
| `contract.py` | **PURE** | **Language-parameterized** — the one structural divergence from OLX. `IMOVELWEB_FIELD_SPECS: dict[str, tuple[FieldSpec, ...]]`; `LANGUAGE_FIELD_ALIASES`; `IMOVELWEB_SAMPLE_BODIES`; `validate_imovelweb_payload(payload, *, language)`; `imovelweb_json_schema(language)`; `contract_summary()`; `diff_observed(bodies, language)`; `IMOVELWEB_RESPONSE_SEMANTICS` (**2xx and 3xx succeed**); `IMOVELWEB_RETRY_POLICY` (`response_timeout_seconds=1.5`, `retry_until_hours=72`, `expired_status="VENCIDO"`, `max_attempts=None`, `duplicates_expected=True`) |
| `webhook.py` | **PURE** | `detect_callback_language(payload)`; `parse_imovelweb_callback(payload, *, language=None) -> ImovelWebLead \| None` — zero IO, never raises, `None` only when there is no event id |
| `normalizers.py` | **PURE** | §5.2 |
| `errors.py` | **PURE** | `ImovelWebError` → `ImovelWebConfigError` (**424**) / `ImovelWebUpstreamError` (vendor status else 502); re-exports the lifted `redact_secrets` |
| `endpoints.py` | **PURE** | Hosts; `IMOVELWEB_SANDBOX_WINDOW`; `IMOVELWEB_ENDPOINT_BASELINE` (every expected status `None`); `IMOVELWEB_PATH_VARIANTS` (both spellings, unresolved); `IMOVELWEB_SWAGGER_PATH`; `IMOVELWEB_REFERENCE_URLS`; `IMOVELWEB_SUPPORT_CONTACTS`. Imports the T1 vocabulary |
| `auth.py` | **IO** | §5.3 |
| `protocol.py` | **IO** | `ImovelWebAdapter` Protocol — §5.4 |
| `fake.py` | **IO** | `FakeImovelWebClient` — in-memory callback config, message store, agency list, `emit_event(...)`. **Mirrors the real client's refusals exactly** (a Fake more permissive than production makes tests lie) |
| `real.py` | **IO** | httpx. `DEFAULT_TIMEOUT_SECONDS = 20.0`, `RATE_LIMIT_BUCKET = "imovelweb"`. **Lenient construction** — no credentials never raises; the first *call* raises `ImovelWebConfigError`. `_is_retryable`: 429 + 5xx + transport only, never 4xx |
| `factory.py` | **IO** | `make_imovelweb_client(*, use_fake=False, client_id, client_secret, region="br", sandbox=False, ...)` |

Pure/IO asymmetry mirrors OLX: the six pure modules are exempt from the
Protocol+Fake+Real+factory quartet; the five IO modules ship it **whole**.

### 5.2 `normalizers.py` — the load-bearing divergence

```python
IMOVELWEB_PIPE = "imovelweb"          # the STABLE external_source. Never varies.
IMOVELWEB_DEFAULT_SOURCE_SLUG = "imovel-web"
IMOVELWEB_ORIGIN_SLUGS = {"Imovelweb": "imovel-web", "CasaMineira": "casa-mineira"}
```

- `leads.external_source` = the constant `"imovelweb"` — the *pipe*, half of
  `uq_sw_leads_org_external_lead`. Varying it with `leadOrigin` would let the
  same `eventId`, re-delivered with a changed or absent `leadOrigin`, silently
  insert a second row.
- `leads.origem_id` = the per-portal `lead_sources` row via
  `resolve_source_slug(lead_origin)`, defaulting to `imovel-web` with a WARNING on
  an unknown value. `wimoveis` folds into `imovel-web`, true value preserved in
  `origem_raw`.

`imovelweb_lead_to_lead_payload(...)` raises `ValueError` on an unparseable
timestamp (`data_entrada` is NOT NULL — refuse to guess), **never assigns a
`corretor_id`**, sets `tipo_lead="novo"`, `contato = full_phone or email`,
`codigo_imovel = client_listing_id`. **`identificationId` (CPF) is deliberately
absent from the projection** (§9).

**Two latent bugs inherited from the OLX normalizer — do not copy blindly:**
- **Timestamp offsets.** Java's `Z` in `yyyy-MM-dd'T'HH:mm:ss.SSSZ` is an RFC-822
  numeric offset (`-0300`), not the literal character.
  `olx_timestamp_to_date` does `.replace("Z", "+00:00")` then
  `datetime.fromisoformat`, which handles `-0300` only on Python ≥ 3.11. Verify
  the runtime version; test `-0300`, `+0000` and a literal `Z`.
- **`data_entrada` timezone.** A 21:30 BRT lead is the *previous* day in UTC.
  `.date()` of an offset-aware datetime is correct — but only if the offset
  arrives. If it does not, convert through `America/Sao_Paulo`; **never default
  to UTC.** The error lands straight in Portal ROI.

### 5.3 `auth.py` — OAuth2 client credentials

- `@dataclass(frozen=True) AccessToken: value, token_type, expires_at, scope, refresh_token, raw`
- `TokenCache` Protocol + `InMemoryTokenCache`, keyed `(base_url, client_id)` so
  sandbox and prod never share a slot.
- `ImovelWebAuth.token()` — cached while `now + REFRESH_SKEW_SECONDS (60) < expires_at`.
- **Single-flight**: one `asyncio.Lock` per cache key. The reconcile job pages;
  without this it logs in once per page.
- `expiration` (absolute) preferred over `expiresIn`. Both **unverified** — units
  and encoding are Gate 0.7; `_parse_expiry` handles all four shapes and WARNs
  when it guesses.
- `logout()` is explicit-only, **never a shutdown hook** — connector and backend
  may share credentials, and one logout revokes the other's token.
- `redact_secrets(text, client_secret, token.value, callback_header_value)` at
  **every** boundary.

Kept vendor-local, not lifted: a generic client-credentials seed module is N=1.
**Trigger recorded:** the second client-credentials vendor lifts this to
`noctusai_lib/integrations/oauth_client_credentials.py`.

### 5.4 `ImovelWebAdapter` Protocol

```
login() / logout()
get_callback_config() -> CallbackConfig
put_callback_config(config) -> CallbackConfig
subscribe_event(event) / unsubscribe_event(event)
list_agency_messages(codigo, *, from_date, to_date=None, page=0, size=100) -> Page[Mensaje]
get_message(id_mensaje) -> Mensaje
list_listing_messages(codigo, codigo_anuncio)
get_contact(codigo, id_contato) -> ContactoRespuesta
get_smartlead(id_mensagem) -> SmartleadRespuesta
get_seeker_profile(user_id_navplat)
list_contact_actions() -> list[dict]
list_agencies(page=0, size=100) -> Page[Inmobiliaria]
unlink_agency(codigo)
emit_event(payload) -> dict          # sandbox only; refuses a non-sandbox base_url
connection_status() -> dict          # ZERO API calls
```

### 5.5 Callback registration

`CallbackConfig.validate()` enforces: `http(s)://` prefix; the literal `"Basic "`
when it is a Basic credential; `lenguajeCallbackBody` ∈ the enum;
`subscriptions ⊆ IMOVELWEB_EVENT_TYPES`; **`subscriptions` non-empty** (legal to
the vendor, useless to us — refuse with a message that says why).

`register_callback(client, *, public_base_url, language, events, rotate_secret=False)`
→ validate → PUT → **GET back** → diff → persist applied + previous → return
`{registered, config, previous, drift}`. The read-back diff is the point: a PUT
that silently drops `subscriptions` is otherwise invisible. The "previous" copy
exists because after a bad PUT the vendor cannot tell you what you had.

Three hazards this design answers:
1. **`PUT /callbacks` is integrator-wide** — no agency in the path, so one bad
   PUT redirects every agency's leads. Confirm-gated in the MCP; an explicit
   admin action in the product; never a startup hook, never the scheduler.
2. **Empty `subscriptions` delivers nothing, silently** — refused at validation,
   and shown red in the health card.
3. **The registered URL is environment-specific** — a dev-tunnel registration
   blackholes production leads with no error anywhere. The register path refuses
   localhost, private ranges and ephemeral tunnel hosts.

Persisted to `app_integration_config` as `imovelweb_callback_config_json` /
`…_previous_json`. **A third config table is not warranted** — one
integrator-wide row.

**Auth scheme — reuse, don't extend:**
```python
webhook_endpoint(
    secret_resolver=_resolve_imovelweb_secret,
    scheme="basic_shared_secret",
    basic_username="noctusai-imovelweb",   # NOT the GRUPO_OLX_BASIC_USERNAME default
    bypass_when_unset=False,
    log_prefix="imovelweb-lead-webhook",
)
```
The `basic_username` argument matters: the default would require ImovelWeb's
header to decode to `vivareal:<secret>`, which is nonsense here.
**Fallback, documented not built:** if the vendor rejects a Basic value at
Gate 1.5, add `WebhookScheme = "static_token"` + `verify_static_token` to
`webhook_signatures.py` — and fix that doc's stale "The four shapes" heading,
which the OLX branch already made wrong by adding a fifth.

### 5.6 Product slice — `products/social-wiring/backend/app/modules/portal_leads/`

Beside `olx_*`, never inside it. This is exactly what the module was named for.

| File | Job |
|---|---|
| `routers/imovelweb_webhook.py` | `POST /leads` (public, token-authed, rate-limited) · `GET /events` · `POST /backfill` · `GET /callback` · `POST /callback/register` · `POST /reconcile` |
| `services/imovelweb_webhook_service.py` | record → resolve org → ingest → drain |
| `services/imovelweb_ingest_service.py` | ledger → unified `leads` projection, idempotent, paged backfill |
| `services/imovelweb_callback_service.py` | §5.5 |
| `services/imovelweb_reconcile_service.py` | the poll-side safety net |
| `scheduler.py` | **extend the existing file** — no second scheduler module |
| `__init__.py` | add `imovelweb_webhook.router` to `ModuleRegistration`; update the docstring — the module now genuinely holds two vendors |

`register()` returns
`ModuleRegistration(routers=[olx_webhook.router, imovelweb_webhook.router], standard_routers=())`.
**Never special-case `app/main.py`** — `_portal_leads` is already in `MODULES`.

**The 1.5 s budget — six consequences:**
1. **Collapse `record_event` to a single write** (`upsert(..., ignore_duplicates=True, on_conflict="id")`).
   ⚠️ `olx_ingest_service.py:9-13` documents that `MockRequestBuilder.upsert()` is
   a **no-op**, so an upsert path **tests green and duplicates live**. Fix the
   mock first (a seed-testing change, same class as the `migration_parser` fix
   already on the OLX branch) or keep read-then-write. **Do not ship an
   untestable upsert.**
2. `RESPONSE_BUDGET_SECONDS = 1.0`; wrap the pre-response section in
   `perf_counter`; WARN on overrun; record it on the event row.
3. Test it as **round-trip count**, not wall clock:
   `assert fake.calls_before_response <= 1`.
4. **No re-fetch by `messageId` in the request path** — background only, behind
   `imovelweb_verify_by_refetch` (default off until measured).
5. **No `imoveis` / agency lookup before responding** — org resolution is
   background work, as OLX already does.
6. Say plainly in the docstring that reconciliation, not the webhook, is the
   durability guarantee.

**Rate-limit review:** `settings.webhook_rate_limit` defaults to `"60/minute"` and
slowapi keys per-IP, so *all* agencies share one bucket — and a 429 is a 4xx,
which starts a 72-hour retry loop. Confirm 60/min clears realistic peak or raise
it for this route. **Keep pin 4; do not drop the limiter.**

**Status-code protocol — divergences from OLX, with reasons:**

| Condition | OLX | **ImovelWeb** | Why |
|---|---|---|---|
| accepted / duplicate | 200 | 200 | |
| malformed JSON, non-object | 200 | 200 | the retry arrives equally malformed |
| no `eventId` | 200 | 200 | no dedup key; a retry cannot help |
| **listing lead without `clientListingId`** | **422** | **200** | ImovelWeb documents no requeue path, and the field is legitimately absent when the listing was never associated. A 4xx would retry for 72 h against a field that will never arrive |
| bad / absent auth header | 401 | 401 | strict, pin-tested |
| unresolvable org | 200 + `unresolved` | 200 + `unresolved` | park, never guess |
| **our durable write fails** | (500 by accident) | **5xx, deliberately** | The vendor retries 72 h and we hold a pull API. A 5xx beats a 200 that loses the lead. **Document it so nobody "fixes" it** |
| 3xx | failure | **success** | Vendor counts 2xx *and* 3xx. Never rely on it; record it |

Background work attaches to `JSONResponse(..., background=background)` with a
`starlette.background.BackgroundTasks()` instance — **never** a `BackgroundTasks`
handler parameter. `@limiter.limit` wraps the endpoint with `functools.wraps`, so
FastAPI resolves annotations against SlowAPI's module globals and raises
`PydanticUndefinedAnnotation` at import, taking the whole app down. Copy the
comment block verbatim from `routers/olx_webhook.py:147-153`.

**Org-resolution chain — never guess:**
1. `codigoImobiliaria` → `imovelweb_agencies.org_id`. **Set `codigoImobiliaria`
   from the org** (its slug, or `noc-<org-uuid-prefix>`) at onboarding, so
   resolution is a pure lookup. Available only if the chosen language carries the
   field — Gate 0.4.
2. `clientListingId` / `reference` → `imoveis.codigo` → `org_id`.
3. `internalReference` → `imoveis.codigo` (secondary — vendor-panel code, may not
   be ours).
4. configured single org (`imovelweb_leads_org_id`).
5. otherwise `status='unresolved'`, `org_id NULL`, **write nothing**.

**Reconciliation:** per authorized agency,
`GET /v2/imobiliarias/{codigo}/mensagens?fromDate=<now-7d>&pageable.*`, paged via
`iter_paged_rows` — never a hand-rolled `while True: range(offset, ...)`. Insert
unseen messages with `source='reconcile'`. Runs on the admin client and
**bypasses RLS**, so every query carries an explicit `.eq("org_id", ...)`; the
agency→org map is the isolation boundary and a bug there is a cross-tenant leak.
⚠️ The response is a `Mensaje` with **no `eventId`** — Gate 0.6 settles the dedup
key, and getting it wrong duplicates every lead.

**Scheduler** (extend `scheduler.py`):
```
imovelweb_leads_retry   */15 * * * *   → ImovelWebWebhookService.drain_pending()
imovelweb_reconcile     17 * * * *     → reconcile_all_agencies()   # offset minute, avoid the :00 herd
```
Both `asyncio.to_thread`-wrapped, both swallowing per-run exceptions with a
WARNING (one bad run must not kill the schedule), both taking DI seams
(`admin_client_factory`, `service_factory`).

**Config** — `app/config.py`: `imovelweb_client_id` · `imovelweb_client_secret` ·
`imovelweb_webhook_secret` · `imovelweb_leads_org_id` · `imovelweb_region` (`br`) ·
`imovelweb_sandbox` · `imovelweb_callback_language` (pending Gate 0.4) ·
`imovelweb_public_base_url` · `imovelweb_verify_by_refetch` (default `False`).
`app_config_store`: matching keys + the two callback-config blobs, a frozen
`ImovelWebConfig` carrier and `resolve_imovelweb_config()` — DB-first per key, env
fallback, graceful degrade on `EncryptionNotConfigured`. Mirror
`resolve_olx_config` **including** its rationale ("a carrier rather than a tuple,
because positional unpacking is how the wrong secret ends up in the wrong
header"). `integration_providers`: an `imovelweb` entry (`oauth_supported: False`,
`manual_entry: True`).

Secret resolver is **per-request**, never captured at import:
```python
async def _resolve_imovelweb_secret(request, body) -> ResolvedSecret:
    from app.services.app_config_store import resolve_imovelweb_config
    return ResolvedSecret(secret=resolve_imovelweb_config().webhook_secret or None)
```

### 5.7 Migration — `0NN_imovelweb_portal_leads.sql`

Number via `noctus.dev.next_migration_number` / `scaffold_migration` — **never
`max+1` by hand**. **File only**; application goes through
`noctus.dev.migrate_product` with explicit tech-lead consent.
`SET search_path = social_wiring, public;`

**Generic idempotency pair — reuse, guarded:**
```sql
ALTER TABLE social_wiring.leads
    ADD COLUMN IF NOT EXISTS external_source  TEXT,
    ADD COLUMN IF NOT EXISTS external_lead_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_leads_org_external_lead
    ON social_wiring.leads (org_id, external_source, external_lead_id)
    WHERE external_lead_id IS NOT NULL;
```
Idempotent whether 051 ran, will run, or never runs. **No `imovelweb_lead_id`
column.**

**`social_wiring.imovelweb_lead_events`** — the durable delivery inbox.
`id TEXT PRIMARY KEY` = the vendor's **`eventId`** (the *delivery* id — **not**
`originLeadId`, the *contact* id, which fans out) · `org_id UUID` **nullable**
(NULL ⇒ `status='unresolved'`) · `event_type` · `codigo_imobiliaria` (indexed) ·
`client_listing_id` · `lead_origin` · `callback_language` (the only forensic
record if the registered language changes vendor-side) ·
`source TEXT NOT NULL DEFAULT 'callback'` CHECK `('callback','reconcile')` ·
`payload JSONB NOT NULL` · `status` CHECK
`('received','processed','error','unresolved','ignored')` · `error` · `attempts` ·
`received_at` · `processed_at`.
Indexes: `(status, received_at) WHERE status IN ('received','error','unresolved')`
(the drain's exact predicate, partial so it stays near-empty) ·
`(org_id, received_at DESC)` · `(codigo_imobiliaria)`.

**`social_wiring.imovelweb_leads`** — lossless typed-core + `raw` ledger.
`id TEXT PK` (eventId) · `org_id UUID NOT NULL` · `event_type` ·
`contact_type_id INTEGER` · `contact_type TEXT` · `origin_lead_id TEXT` ·
`message_id BIGINT` · `lead_origin` · `origin_listing_id` · `client_listing_id` ·
`internal_reference` · `codigo_imobiliaria` · `id_navplat_development BIGINT` ·
`development_code` · `name` · `email` · `ddd` · `phone` · `phone_number` ·
`message` · `user_id_navplat` · `lead_timestamp TIMESTAMPTZ` ·
`smartlead JSONB` (nullable, fetched later) · `raw JSONB NOT NULL` · `synced_at`.
**No `identification_id` column** (§9).
Indexes: `(org_id, lead_timestamp DESC)` · `(client_listing_id)` ·
`(origin_lead_id)` (contact→events fan-in) · `(message_id)` (reconcile dedup).

**`social_wiring.imovelweb_agencies`** — `codigo_imobiliaria TEXT PK` ·
`org_id UUID NOT NULL` · `razao_social` · `authorized_at` · `last_seen_at` ·
`raw JSONB` · index on `(org_id)` (**not unique** — one org may hold several
agency codes). A third table beyond the two-per-vendor rule, justified: it *is*
the org-resolution key, it is per-org and multi-row, and it cannot live in
app-wide config.

**RLS on all three:**
```sql
ALTER TABLE social_wiring.<t> ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "<t>_select_own_org" ON social_wiring.<t>;
CREATE POLICY "<t>_select_own_org" ON social_wiring.<t>
    FOR SELECT TO authenticated USING (org_id = public.current_org_id());
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.<t>;
CREATE POLICY "service_role_bypass" ON social_wiring.<t>
    FOR ALL TO service_role USING (true) WITH CHECK (true);
```
The **literal** name `service_role_bypass` — the keeper matches on it. Prefer
`noctusai_lib.sql.service_role_bypass(table, schema="social_wiring")`.

**`integration_accounts.provider` CHECK** — widen with `'imovelweb'` using the
**dynamic-lookup `DO $$` block** from 051 (declared inline in migration 005, so
the constraint name is whatever Postgres generated *on that database*; a named
`DROP CONSTRAINT IF EXISTS` silently no-ops and the `ADD` then fails).
⚠️ **Ordering hazard:** two migrations now rewrite this CHECK by dynamic lookup and
the later one wins — so the ImovelWeb list must be a **superset**:
`'youtube','google_drive','gmail','meta','n8n','instagram','olx','imovelweb'`.
State it in the migration comment.

**`lead_sources` — no migration change.** `imovel-web` already exists in
`app/modules/leads/seed_data.py:68` with five alias rows.

### 5.8 MCP connector — `mcp/imovelweb/`

Composes `mcp/_kit` (`bootstrap`, `settings`, `registry`, `errors`, `transport`,
`seed_pin`). **Do not copy `mcp/vista`.** `prepare_sys_path(__file__)` must
precede the first `noctusai_lib` import: an editable install registers a
meta-path finder consulted before `sys.path`, so without it the server boots in
the primary checkout and dies in every worktree — which is where it gets
developed (`mcp/olx/server.py:42-50`).

```
mcp/imovelweb/{server,settings,api,client,types}.py
mcp/imovelweb/tools/{auth,callbacks,leads,agencies,sandbox,contract,diagnostics}.py
mcp/imovelweb/tests/{__init__,conftest,test_smoke}.py
mcp/imovelweb/fixtures/observed/.gitkeep · README.md · .env.example
```

**READ · zero-IO · no credentials:** `imovelweb.contract.describe(language)` ·
`.validate_payload` · `.diff_observed` · `imovelweb.diagnostics.list_known_endpoints`
**READ · credentialed:** `.connection_status` (zero API calls) · `.probe` ·
**`.fetch_swagger`** (downloads the public spec from prod *and* sandbox and diffs
both against `endpoints.py` — a tool the OLX connector could not have) ·
`imovelweb.callbacks.get_config` · `imovelweb.agencies.list` ·
`imovelweb.leads.{get_message,list_messages,get_smartlead,list_contact_actions}`
**WRITE · confirm-gated (412 before any side effect):**
`imovelweb.callbacks.put_config` (⚠️ integrator-wide; must echo the read-back diff
and the previous config) · `.subscribe` / `.unsubscribe` ·
**`imovelweb.sandbox.emit_event`** (**hard-refuses** a non-sandbox host; surfaces
the 07:00–21:00 UTC-3 window as a typed error, not a mystery timeout) ·
`imovelweb.webhook.record_delivery` (keyed by event id; record unparseable bodies
under a hash — they are the most valuable evidence) · `imovelweb.webhook.simulate`

Every result passes `redact_secrets(text, client_secret, token, callback_header_value)`.
`imovelweb.leads.get_message` / `.get_smartlead` redact `identificationId` by
default; `include_pii=true` is an explicit opt-in.

⚠️ **`.mcp.json` is gitignored.** Never register the connector before the merge
into `dev` — the row's `cwd` points at the primary checkout, whose editable
`noctusai_lib` has no `integrations.imovelweb` until then, and the server
`ImportError`s at every session start. Document the row in
`KB § MCP-SERVERS/imovelweb.md`; drive it from the worktree over stdio.

### 5.9 Frontend

`src/hooks/useImovelWebLeads.ts` — `useImovelWebEvents(limit)` ·
`useImovelWebBackfill()` · `useImovelWebCallbackConfig()` ·
`useRegisterImovelWebCallback()` · `useImovelWebReconcile()`. **Loading gated on
`isPending || isFetching`, never `isLoading`** — under TanStack v5 `isLoading` is
false during a background refetch, so an `isEmpty` branch renders "no deliveries
yet" over deliveries that exist, which here reads as *"the integration is dead"*
at exactly the moment it is working (keeper `check_lying_loading_state`). Derive
`stuck` and `reconcileShare` once in the hook so every consumer agrees.

`src/pages/leads/components/ImovelWebWebhookCard.tsx` — mirrors
`OlxWebhookCard.tsx` plus a **callback-configuration panel**: (1) stuck count
first; (2) subscriptions, red when empty — *"Nenhum evento assinado — nada será
entregue"*; (3) registered URL vs ours, red on mismatch, copy-to-clipboard;
(4) language + header key, so a vendor-side change is visible; (5) "Registrar /
Atualizar" behind a confirm dialog naming the blast radius (*"afeta TODAS as
imobiliárias"*); (6) delivery source split (callback vs reconcile) — a rising
reconcile share is the operator-visible symptom of a missed 1.5 s budget;
(7) complete loading / empty / error / success states.

Mount beside `<OlxWebhookCard />` in `src/pages/leads/Configuracao.tsx`.
`Origens.tsx` needs no change — already source-generic.

### 5.10 DRY triage (`noc-triage` verdicts)

| # | Recurrence | N | Verdict |
|---|---|---|---|
| **T1** | Endpoint-probe status vocabulary | **3** (vista · olx · imovelweb) | **[F] MUST formalize.** `integrations/olx/endpoints.py:26-32` already carries the obligation in a comment. Lift to `noctusai_lib/integrations/endpoint_status.py`; rewrite `vista/client.py` + `olx/endpoints.py` to import it |
| **T2** | Secret redaction at the boundary | **3+** | **[F] MUST formalize.** Lift to `noctusai_lib/integrations/redaction.py::redact_secrets(text, *secrets)` with the `len >= 4` guard; keep `redact_api_key` / `redact_secret` as thin aliases (lossless-refactor) |
| **T3** | Shared `portal_lead` normalization primitive | **2** | **[A] Accept the fork, with a named trigger.** Six semantic differences land exactly where a shared abstraction would need parameters: the dedup key is a different *concept* (delivery vs lead); `leadOrigin` semantics invert (never-names-the-portal vs always-does); a missing listing id means opposite things (4xx requeue vs 200); ImovelWeb's field *names* are configuration; CPF is a whole LGPD class OLX lacks; and a pull API changes the durability architecture, not just the parser. The genuinely-shared thing is the **output shape** — already de-facto shared, already tested twice. **Trigger, as a comment atop `imovelweb/normalizers.py`:** *the third portal receiver, **or** the first commit that must change both `olx/normalizers.py` and `imovelweb/normalizers.py` for the same reason, forces the lift* |
| **T4** | ISO-date → `date` helper | verify | `olx_timestamp_to_date` says it mirrors `meta_ingest_service`. Grep for a third; if N≥3, **[F]** lift to a shared `parse_iso_date` — but fix the offset bug first (§5.2) |

---

## 6. Implementation phases

### Phase A0 — Findings handed off to the OLX branch owner 🅿️ *(not ours to apply)*

> **Ownership rule (user, 2026-08-17): do not touch work that is not yours.**
> Parallel agents are live, and the last to finish handles merging. Everything
> below lives inside `feat/olx-portal-leads-mcp`'s active file set, so this phase
> **records** the findings and does not apply them. They are surfaced to that
> branch's owner; if the branch is abandoned, they fold into §8 contingency (b).

- [ ] **Handed off — vendor-identity framing.** The OLX artifacts read as if
      ZAP · VivaReal · OLX · ImovelWeb · Casa Mineira were one *vendor*. They are
      one *pipe*; ImovelWeb and Casa Mineira are Navent / Grupo QuintoAndar. The
      bridge in `KB § INTEGRATIONS/olx.md` §0 is real and should be **qualified,
      never deleted** (lossless-refactor). Affects `olx.md` §0/§9,
      `integrations/olx/{__init__,types,endpoints}.py`, `portal_leads/__init__.py`,
      `migrations/051_*.sql` header, `mcp/olx/server.py`,
      `KB § MCP-SERVERS/{README,olx}.md`, and
      `projects/olx-portal-leads-ingestion/HANDOFF.md` (whose ImovelWeb-direct
      hypothesis is now refuted).
- [ ] **Handed off — 051's service-role policies are keeper-invisible.** They are
      named `olx_lead_events_service_role` / `olx_leads_service_role`, but
      `check_admin_endpoint_service_role_bypass` matches the **literal** name
      `service_role_bypass` (see `products/core/backend/migrations/030_*.sql:13`;
      98 policies repo-wide use the literal). 051 is unmerged, so it is a free fix
      for its owner. **Our migration uses the literal name regardless.**
- [ ] **Handed off — `routers/olx_webhook.py:172` does `.select("*")`** on the
      events table, returning the full lead payload to any authenticated org
      member. Tolerable for the OLX payload; fatal for ours, which carries a CPF —
      so our `GET /events` selects an explicit column list. Their call.
- [ ] **Ours, deferred to Phase A** — T1/T2/T4 lifts touch `vista/client.py` and
      `olx/endpoints.py`, both outside our tree. Build the ImovelWeb shell with
      **local** `endpoint_status` + `redaction` helpers first; lift to
      `noctusai_lib/integrations/{endpoint_status,redaction}.py` and rewrite the
      two call sites only once the OLX branch has landed. The N≥3 obligation is
      real and recorded — it is *sequenced*, not waived.

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`._

### Phase A — Seed package ✅ *(2026-08-17 · 220 tests green by exit code)*
- [x] `integrations/imovelweb/{__init__,types,contract,webhook,normalizers,errors,endpoints}.py` (pure)
- [x] `integrations/imovelweb/{auth,protocol,fake,real,factory}.py` (IO — the full quartet, no half-ship)
- [x] `tests/integrations/imovelweb/` — the eight suites as specified, plus `test_receiver_credential`
- [x] Every `FieldSpec.verified=False`, every baseline expected status `None`

**Improvements:**

1. **Two bugs the tests caught, both fixed in the CODE.** `full_phone` produced
   `31+5531999998888`, because the vendor documents `phone` as
   international-with-`+` *and* `phoneNumber` as "ddd + phone" — both cannot
   hold. The resolution order is now phoneNumber → an already-prefixed phone →
   bare-local concatenation, and the contradiction is vendor question 18.
   Separately, the timezone guard in `imovelweb_timestamp_to_date` was
   decorative: `.date()` on an aware datetime already yields the local date, so
   `replace(tzinfo=BR)` did nothing. The real safeguard is negative — never
   `.astimezone(utc)` before `.date()` — and the docstring now says that, with a
   23:30 BRT test pinning it.
2. **The inbound credential moved into the seed** (`basic_credential`,
   `receiver_url_problems`, `IMOVELWEB_BASIC_USERNAME`) rather than living in its
   first caller. The connector, the receiver and the register service must agree
   on it byte-for-byte; a local copy in any one of them is a fork whose only
   symptom is a 401 nobody can explain.
3. **No model call anywhere on the lead path** — a design principle added after
   a run of upstream API errors during this project. The vendor allows 1.5 s to
   answer; a model call cannot fit, and a model *outage* inside that window would
   convert someone else's incident into lost customer enquiries. A test walks the
   package's own imports and fails if anything reaches a model provider, so the
   rule is mechanical rather than remembered.

### Phase B — MCP connector + ops doc ✅ *(2026-08-18 · 19 tools · 79 tests green by exit code)*
- [x] `mcp/imovelweb/**` per §5.8, composing `mcp/_kit`
- [x] `mcp/imovelweb/tests/test_smoke.py` — every registry tool; 412 asserted **before** any side effect (proven with a client that raises on ANY call); 424 when unconfigured; the sandbox guard refuses a prod host
- [x] `KB § MCP-SERVERS/imovelweb.md` + a section in `KB § MCP-SERVERS/README.md`; registration row **documented, not applied**
- [x] Driven over real stdio from the worktree: `initialize` → `tools/list` (19) → `contract.describe` (answers with no credentials) → `callbacks.put_config` with no `confirm` (typed 412, `registered: false`, nothing called)

**Improvements:**

1. **The write-tool list is pinned to the descriptors, not maintained beside
   them.** `test_write_tools_are_all_declared_here` derives the write set from
   the descriptions and asserts it equals the list the confirm-gate test
   iterates. A new write tool that nobody remembered to add would otherwise slip
   past the gate test silently — the exact failure the gate exists to prevent.
2. **Redaction became policy rather than a log helper.** Results are serialized,
   stripped of all three secrets, and re-parsed, so a secret embedded mid-string
   is caught as well as one in its own field; a value that cannot be serialized
   RAISES rather than being returned unredacted. `identificationId` is replaced
   with a placeholder and the KEY is kept, so the fact that a CPF arrived stays
   visible even when its value does not.
3. **`webhook.simulate` measures the 1.5-second budget locally.** That budget is
   the single most design-forcing fact in this integration, and until now it
   could only be measured at Gate 1 against the vendor. Measuring it against our
   own receiver makes it available from Phase C onward, which is when the handler
   shape is still cheap to change.
4. **Ordering discovered while building:** `imovelweb.contract.diff_observed` as a
   handler name shadowed the seed function imported into the same module, and the
   test that reached for the handler by attribute got the seed function instead.
   Fixed by aliasing the import — a module that exports two different things under
   one name is a trap for the next reader, not just for a test.
5. **The connector found a defect in itself on its first live run.** Pointed at
   the real public spec, `fetch_swagger` returned 403 from both hosts and reported
   "network or DNS on our side". The actual cause: the vendor's edge 403s
   `Python-urllib/*` by name — the same URL answered 200 to curl seconds later.
   Fixed by sending an identifying User-Agent (no browser impersonation needed;
   an honest `noctusai-imovelweb-connector/1.0` is accepted) and by classifying a
   401/403 on a public endpoint as a client rejection rather than a missing spec.
   Worth noting as a class: a diagnostic tool that misattributes a failure is
   worse than one that fails, because it sends an operator to the wrong layer
   with confidence.

### Phase Gate-0 — Spec-only verification ⏳ *(ran 2026-08-17, re-run through the connector 2026-08-18; 5 of 9 settled, 4 provably NOT answerable without credentials)*

**The headline: Gate 0 is much smaller than planned, and knowing why is the finding.**
Two structural facts, both discovered by running it:

1. **The Swagger spec contains ZERO callback-body definitions.** It models only
   the API *we call*. Grepping every definition for `eventId` / `idEvento` /
   `tipoEvento` / `eventType` / `leadOrigin` / `originLeadId` / `clientListingId`
   returns an empty set. The pushed bodies are **prose-only**, so the language
   question cannot be settled from the spec — it moves to Gate 1.7, where an
   emitted event is observed. *This vindicates the language-parameterized
   `contract.py`: the design survives not knowing, which a hardcoded single-language
   parser would not have.*
2. **`/v1/**` returns 401 before routing.** Spring Security's filter chain runs
   ahead of the dispatcher, so a bogus `/v1/definitely-not-a-real-endpoint-xyz`
   also answers 401 (while `/nope`, outside the secured pattern, answers 404).
   **An unauthenticated probe therefore cannot discriminate a real path from a
   typo** — which retires the whole "probe both spellings" idea and is worth
   remembering before designing any future probe against this vendor.

- [x] **0.1 ✅** Both specs download unauthenticated. Prod `api-br-open.navent.com` → `2.105.01-RC1`; sandbox `api-br-sandbox-open.navent.com` → `ON-10172`. Path sets are identical **except** the sandbox exposes `POST /v1/callbacks/geracao/eventos`, which prod does not.
- [x] **0.2 ✅ SETTLED 2026-08-18** via `imovelweb.diagnostics.fetch_swagger`. `/v1/configuracao/callbacks` is present on both hosts with `get` and `put`; `/v1/configuracion/callbacks` is absent from both specs entirely. The Spanish spelling is a documentation artefact. Kept in `IMOVELWEB_PATH_VARIANTS` rather than deleted: the spec is generated from the running code, so absence is strong evidence but not proof of no alias controller. Gate 1 retires it.
- [x] **0.3 ✅ SETTLED 2026-08-18**, same run. `/v1/callbacks/geracao/eventos` is present with `post`, on the **sandbox host only**; `/v1/callbacks/generacion/evento` is absent from both. Same treatment.
- [ ] **0.4 ❌ MOVED TO GATE 1.7.** Whether the EN2 body carries an agency code cannot be read from the spec (finding 1). **It no longer blocks Phase A** — `contract.py` is language-parameterized by design — but it *does* block the runtime `imovelweb_callback_language` default and org-resolution rung 1.
- [ ] **0.5 ❌ MOVED TO GATE 1.7.** Same reason. The five variants stay transcribed from prose, every `FieldSpec.verified=False`.
- [ ] **0.6 ❌ MOVED TO GATE 1.12.** `Mensaje.id` / `idMensaje` vs the callback's `eventId` / `messageId` needs live data from both surfaces. Still the reconcile-dedup blocker.
- [x] **0.7 ✅** `OAuth2AccessToken.expiration` is `string` / `format: date-time` (ISO-8601); `expiresIn` is `int32` (seconds, per OAuth2 convention); `refreshToken` is `OAuth2RefreshToken {value}` and carries **no expiry of its own**. So `_parse_expiry` handles **two** shapes, not four: prefer `expiration`, fall back to `now + expiresIn`. Confirm `expiration` is actually populated at Gate 1.2.
- [ ] **0.8 ❌ MOVED TO GATE 1.2.** Whether login accepts `Authorization: Basic` + a form body cannot be tested — the grant handler never runs unauthenticated.
- [x] **0.9 ✅** `ConfiguracionCallback` carries `subscriptions: string[]`, so a single `PUT /v1/configuracao/callbacks` **can** set URL + header + language + subscriptions atomically; `PUT /callbacks/{evento}` is the incremental path. Register atomically, then read back and diff.
- [x] **0.11 ✅ (new, unplanned — 2026-08-18)** **Every endpoint we had written down exists.** 15/15 baseline rows confirmed against the generated spec, `in_baseline_not_in_spec` empty. The same diff caught two endpoints the ADAPTER calls that the baseline had not listed (`/v1/imobiliarias/{cod}/mensagens`, `/v1/imobiliarias/{cod}/anuncios/{cod}/mensagens`) — the baseline was not a complete map of our own client, and now is.
- [x] **0.12 ✅ (new, unplanned — 2026-08-18)** **The vendor's edge 403s `Python-urllib/*` by name.** The public spec answered 200 to curl and 403 to urllib from the same machine, seconds apart. The connector now sends an identifying User-Agent and classifies a 401/403 on this public endpoint as a client rejection rather than "not served" — otherwise the tool blames our network for a WAF decision and an operator debugs the wrong layer.
- [x] **0.13 ✅ (new, unplanned — 2026-08-18)** **40 spec endpoints sit outside our baseline, and they are almost entirely the listing-publication surface** (`anuncios`, `lancamentos`, `multimidia`, `tipopropriedade`, `locais`, `imobiliarias/{}/usuarios`). That is not scope we missed: it overlaps `products/erp-imobiliario`'s outbound XML feed and needs Read-and-Write credentials. It sharpens open question 19 — the ReadOnly-vs-Read-and-Write decision buys or forfeits this whole surface, not just the `AVISO_*` events.
- [x] **0.10 ✅ (new, unplanned)** **Errors are XML, not JSON.** A 401 returns `Content-Type: application/xml` with `<UnauthorizedException><error>unauthorized</error><error_description>…</error_description></UnauthorizedException>`, despite `produces: */*`. `real.py` must not assume a JSON error envelope — parse defensively and fall back to the raw text, or every upstream failure surfaces as a confusing decode error instead of the vendor's actual message.

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`._

### Phase Gate-1 — Sandbox verification 🅿️ *(blocked on user: request sandbox credentials from `integracao@imovelweb.com.br`)*
- [ ] 1.1 `connection_status` answers from a live session
- [ ] 1.2 Login succeeds; token works as `Authorization: Bearer` (record which form)
- [ ] 1.3 `probe` — every row `as_expected` or **corrected in `endpoints.py` from what was observed**, never guessed
- [ ] 1.4 `agencies.list` returns ≥1 authorized agency; the login-button onboarding is exercised end-to-end, confirming **we** choose `CODIGOIMOBILIARIA`
- [ ] 1.5 `callbacks.put_config confirm=true` registers our sandbox receiver with our Basic header; `get_config` reads it back **identically**
- [ ] 1.6 `subscribe(CONTACTO)` + `subscribe(CONTACTO_MENSAJE)` appear in the read-back
- [ ] 1.7 **`sandbox.emit_event` delivers a `CONTACTO_MENSAJE` to our receiver; we answer 200; `record_delivery` captures the body.** Repeat for `CONTACTO`
- [ ] 1.8 `contract.diff_observed` reports **zero unexplained divergence**; every divergence is fixed in `contract.py` first and dated in the KB change log
- [ ] 1.9 **Measure real pre-response latency. p99 > 1.5 s ⇒ the handler shape is wrong; surface-note and revisit §5.6 before Phase C is trusted**
- [ ] 1.10 Deliberately answer non-2xx once; observe the retry cadence + the `VENCIDO` transition
- [ ] 1.11 `GET /v1/contatos/acoes` replaces the transcribed `IMOVELWEB_CONTACT_TYPES`
- [ ] 1.12 Reconcile a lead: emit, blackhole the callback, run reconcile, prove it lands **exactly once**
- [ ] 1.13 Confirm the real timestamp offset format

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`._

### Phase C — Product slice ✅ *(2026-08-18 · 2092 passed / 3 skipped by exit code)*
- [x] Migration `052_imovelweb_portal_leads.sql` per §5.7 — **file only, not applied**
- [x] `routers/imovelweb_webhook.py` + four services + `scheduler.py` extension + `__init__.py` registration
- [x] `app/config.py`, `app_config_store.py`, `integration_providers.py`, and the `portal_leads/deps.py` config seam extended for a second vendor
- [x] Kept read-then-write, with a `NOC-REMEDIATE[perf-single-write]` marker — never an untestable upsert
- [x] `tests/modules/portal_leads/test_imovelweb_*` — the four mandated webhook cases, the auth boundary at strict `== 401`, the four service suites (109 tests)
- [ ] Security-advisor consult on the diff *(deferred to Gate 2 with the LGPD review — nothing is live yet)*

**Improvements:**

1. **The mock's `upsert()` decided the shape, and the decision is recorded
   rather than silent.** Collapsing `record_event` into one write is the
   obvious answer to a 1.5-second budget, but `MockRequestBuilder.upsert()`
   is still a no-op, so an upsert path tests green and duplicates live.
   Teaching it conflict-target propagation changes test behaviour at ~70 call
   sites across the fleet — its own piece of work, not a side effect of this
   one. So: read-then-write, a `NOC-REMEDIATE[perf-single-write]` marker
   naming the prerequisite, budget instrumentation, and a test asserting the
   ROUND-TRIP COUNT (deterministic) rather than wall-clock latency (flaky) —
   because the count is what actually changes when someone adds one more
   lookup to the request path.
2. **A duplicate class the OLX pipe cannot have, closed without waiting for
   the vendor.** A pulled `Mensaje` has no `eventId`, so reconciliation mints
   a synthetic key and the same enquiry can arrive twice under two ids.
   Whether the two id spaces relate is Gate 0.6, still unanswered — but
   `messageId` closes it regardless, and it is present on exactly the class
   where the overlap can happen, since reconciliation only ever pulls
   MESSAGES. The ledger keeps both deliveries; only the projection dedupes.
3. **Consumed rather than forked, after grepping first.** The `portal_leads`
   config seam (extended for a second vendor, not copied), the seed's
   `receiver_url_problems`, and `iter_paged_rows`. The OLX branch's
   `portal_split` rule table was evaluated and deliberately NOT consumed: it
   infers an unknown portal from an unknown discriminator, while this vendor
   names the portal outright, so routing through it would mean writing
   `evidence` strings for a documented field.
4. **Two tests were wrong and got fixed as tests, not by weakening the
   code.** A zero-budget latency assertion failed because sub-0.1ms work
   rounds to 0.0; and a "contact fan-out" case reused one `messageId`, which
   is the same message twice — the guard collapsed it correctly.

### Phase D — Frontend slice ✅ *(2026-08-18 · 629 tests, tsc + build clean by exit code)*
- [x] `useImovelWebLeads.ts` (+ 16 tests) — `isPending || isFetching`, derived `stuck` + `reconcileShare`
- [x] `ImovelWebWebhookCard.tsx` (+ 17 tests) — the panels of §5.9, including the callback-configuration panel
- [x] Mounted in `Configuracao.tsx`; `npx vitest run && npm run build && npx tsc --noEmit` all exit 0

**Improvements:**

1. **`reconcileShare` is `null`, not `0`, when nothing has arrived.** Zero
   would render as "the fast path is working" when there is simply no data —
   the same class of lie as the loading-state trap, one level up.
2. **"Not registered yet" is deliberately not red.** Only a MISMATCH is a
   fault. Colouring first-time setup as a failure teaches an operator to
   ignore the colour, which costs the two states that genuinely are red.
3. **Two house facts learned the hard way, fixed in the code:** this project
   wires no jest-dom matchers (`toBeTruthy()` is the style), and the
   design-system `Skeleton` does not forward arbitrary props — a
   `data-testid` on it vanishes silently, which would have made that
   assertion test nothing at all.

### Phase Gate-2 — Production verification 🅿️ *(blocked on user: production credentials)*
- [ ] 2.1 Prod login + probe; baselines corrected for prod
- [ ] 2.2 Callback registered at the **real public URL** — the localhost guard is exercised and refuses first
- [ ] 2.3 ≥1 **real** inbound delivery captured; `diff_observed` clean; `verified` flags flipped; KB §8 dated with evidence
- [ ] 2.4 Observed `leadOrigin` values recorded
- [ ] 2.5 Rate limits observed — record the 429s, or record that none appeared over N calls
- [ ] 2.6 Cross-pipe duplicate check: is this advertiser also live on Gestor de Leads?
- [ ] 2.7 LGPD flags reviewed, closed or accepted in writing
- [ ] 2.8 Migration applied via `noctus.dev.migrate_product` with explicit consent

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`._

### Phase E — Integration ⏳ *(the rebase is DONE; the bless waits on Gate 2)*
- [x] **Rebased onto `origin/dev` 2026-08-18** — the OLX branch had already merged, so contingency (a) applied and the ten commits replayed clean. Everything from Phase C onward was built ON the merged tip, not on a stale base.
- [x] Every suite re-run after the rebase: seed 3188/1-skipped, MCP 146, product backend 2092/3-skipped, frontend 629, tsc + build. All by exit code.
- [ ] Final re-run at bless time — per-branch green ≠ integration green, and `dev` moves
- [ ] Register the `.mcp.json` row (post-merge only)
- [ ] Eight-way sync verified; `noctus.hound.scan` clean

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`._

**Wave order** — A0 → A → B → **Gate 0** → **Gate 1** → C ∥ D → **Gate 2** → E.
This **reorders** the OLX project's waves: because the sandbox simulator makes
Gate 1 achievable without real traffic, the product slice does not wait on
production credentials.

---

## 7. Open questions

**For the user / tech-lead**
1. **`AVISO_*` scope** — read/write credentials are required to receive listing
   events, and they also grant us publish/unpublish on ImovelWeb. Accept that
   blast radius, or ship ReadOnly and drop the `AVISO_*` leg? *Needs an answer
   before the Gate-1 credential request. Recommendation: **ReadOnly first**; the
   lead legs deliver the value, and read/write can be requested later without
   rework.*
2. **Do we store the CPF at all?** *Needs an answer before Phase C's migration.
   Recommendation: **no** — Art. 6.III minimization, and no current feature uses
   it. If yes: a dedicated column, a documented TTL, and exclusion from the
   `authenticated` SELECT.*
3. **Is any advertiser also live on the Grupo OLX pipe for ImovelWeb?** *Needs an
   answer at Gate 2. If yes, cross-pipe duplicates are immediate (§5).*
4. **`codigoImobiliaria` derived from the org, or whatever the agency already
   uses?** *Needs an answer before Phase C. Recommendation: **derive** — it makes
   resolution rung 1 a pure lookup.*
5. **`imovelweb_lead_events` / `imovelweb_leads` retention TTL — what N?** *Needs
   an answer before Phase C. Recommendation: null `payload` / `raw` after 90 days
   for `status='processed'`, **keep the row** — the id is the dedup key, and
   deleting it lets a late redelivery re-ingest.*
6. **A `wimoveis` `lead_sources` slug now, or fold into `imovel-web`?**
   *Recommendation: **fold** — no observed BR traffic; minting a slug for an
   unseen value records a guess as data.*
7. **Will the OLX branch merge?** *Flips §8's contingency from (a) to (b) and adds
   ~200 lines of re-authoring.*

**For the vendor** (`integracao@imovelweb.com.br` · `open@navent.com` · the Jira portal)
8. Rate limits — undocumented. What is the ceiling for
   `GET /v2/imobiliarias/{cod}/mensagens` during a backfill?
9. Is the OAuth token scoped to the integrator or to an agency? Can one token
   serve all authorized agencies?
10. Token lifetime; is `refreshToken` usable, or is re-login the intended path?
11. Callback config is integrator-wide — is a **per-agency** callback URL
    possible? *(It would make org resolution trivial and remove an entire failure
    class.)*
12. `clientListingId` — the docs contradict themselves: omitted when the listing
    *was* associated, or when it *was not*?
13. `configuracao` vs `configuracion` — which is live on the BR host, and is the
    other an alias?
14. Simulator path — `geracao/eventos` or `generacion/evento`?
15. `Mensaje.id` / `idMensaje` vs the callback's `eventId` / `messageId` — same id
    space?
16. Does the vendor deliver from a fixed IP range? *(Would let us add an
    allowlist on top of a scheme with no body binding.)*
17. Is there a delivery-status API (which events are `VENCIDO`) so losses are
    detectable proactively rather than by reconciliation?
18. **EN2 vs PT** — which is recommended for a multi-tenant integrator, and does
    EN2 carry an agency code?

---

## 8. Dependencies & blockers

**Six hard dependencies exist only on `feat/olx-portal-leads-mcp`:**
- `basic_shared_secret` scheme + the `WebhookScheme` literal + the
  `_DEFAULT_SIGNATURE_HEADER` row — `noctusai_lib/security/webhook_signatures.py`
- `app/modules/portal_leads/` package + `register()` + the `MODULES` entry
- `leads.external_source` + `external_lead_id` +
  `uq_sw_leads_org_external_lead` — `migrations/051_olx_portal_leads.sql`
- `noctusai_lib.integrations.persistence.iter_paged_rows`
- the `noctusai_lib.testing.migration_parser` multi-`ADD COLUMN` fix
- the `resolve_olx_config` shape + the `integration_providers` extension precedent

**Contingencies**
- **(a) OLX lands in `dev` first (expected).** `git rebase origin/dev`
  fast-forwards the shared commits. **Re-run every gate on the merged tip.**
- **(b) OLX never lands.** Cherry-pick the `basic_shared_secret` commit verbatim;
  re-author `portal_leads/__init__.py` + the `MODULES` entry (~36 lines); move the
  `leads.external_source` block into the ImovelWeb migration (already written
  `IF NOT EXISTS`-guarded for exactly this), including the Meta backfill `UPDATE`
  with its `AND external_lead_id IS NULL` guard; cherry-pick `iter_paged_rows`
  and the `migration_parser` fix.
- **(c) OLX lands changed.** Rebase, then **re-read `webhook_signatures.py`**
  before assuming the scheme signature is unchanged.
- **(d) The sibling agent is still active on the OLX branch.** Expect conflicts;
  they get resolved at merge time by whoever merges. Do not edit OLX files
  outside the Phase-A0 list.

**External blockers**
- **Sandbox credentials** — email `integracao@imovelweb.com.br`. Gate 1 cannot
  start without them. Sandbox is up only ~07:00–21:00 UTC-3.
- **Production credentials** — a second email after sandbox testing. Gate 2.
- **Agency authorization** — each imobiliária must click through the vendor's
  login button before its leads flow.
- **`.mcp.json` registration** must wait for the merge into `dev`.

---

## 9. Success criteria

- A `CONTACTO_MENSAJE` emitted by the sandbox simulator arrives at our receiver,
  is answered 200 **within the measured budget**, and lands in `leads` with the
  right `org_id`, the right `origem_id`, and `external_source='imovelweb'`.
- The same event delivered twice — once by callback, once by reconciliation —
  produces **exactly one** `leads` row.
- A lead whose callback never arrives is recovered by the hourly reconcile job
  inside the 72-hour window.
- `imovelweb.contract.diff_observed` reports zero unexplained divergence, and
  `contract_summary()["verified_against_live_traffic"]` is `True` with a dated
  §8 change-log entry backing it.
- The health card shows red for an empty `subscriptions` list and for a
  registered-URL mismatch, and the register action refuses a localhost URL.
- No CPF appears in `leads`, in any API response, or in any log line.
- A cross-tenant test with two agencies in two orgs shows no crossover under the
  admin-client reconcile path.
- All suites green **on the merged tip**: seed, `mcp/imovelweb`, social-wiring
  backend (baseline 1942 passed / 3 skipped), social-wiring frontend
  (596 passed), `tsc --noEmit` rc=0, `--verify-kb-sync` rc=0.

**Test contract** — the four mandated webhook cases, all status-code-pinned:
`test_valid_token_returns_200` · `test_wrong_secret_returns_401` (**substituted
for the KB template's "tampered body"** — `basic_shared_secret` has no body
binding, so a tampered-body test would be meaningless; paired with
`test_tampered_body_with_valid_token_returns_200`, which *documents the weakness*
rather than pretending it is covered) · `test_missing_authorization_header_returns_401` ·
`test_unset_secret_returns_401_not_bypass` (**the inverse of the template's fourth
case**, because `bypass_when_unset=False` — pin it *and comment why*, so a
reviewer does not "fix" it back). Plus
`test_custom_header_name_is_honoured` · `test_missing_client_listing_id_returns_200_not_422` ·
`test_response_makes_at_most_one_round_trip` · `test_durable_write_failure_returns_5xx` ·
`test_3xx_is_documented_as_success`.

**Verification commands** (verify by exit code — never a piped `tail`):
```
cd seed/lib/backend                && python -m pytest tests/integrations/imovelweb tests/security -q
cd mcp                             && python -m pytest imovelweb/tests -q && python -m pytest _kit/tests -q
cd products/social-wiring/backend  && python -m pytest -q
cd products/social-wiring/frontend && npm test && npm run build && npx tsc --noEmit
python mcp/noctusai/cli.py --verify-kb-sync
python mcp/noctusai/cli.py --check-claude-md-router
```

---

## 10. How to use this plan

Standard protocol (live-tick, phase-by-phase, revise when understanding changes,
commit plan changes with the code). Three project-specific notes:

- **Start at Phase A0, then Gate 0 — not Phase A.** Gate 0 needs no credentials
  and settles the language choice, which reshapes `contract.py`, `webhook.py`, the
  resolution chain and the migration. Writing the parser first risks rewriting all
  four.
- **Never flip a `verified` flag from a document.** Only an observation flips it,
  and the observation gets dated in `KB § INTEGRATIONS/imovelweb.md` §8.
- **The four surface triggers in §4a.4 BLOCK.** They are the cases where
  proceeding on the dispatched route produces silently-wrong data — duplicated
  leads, cross-tenant writes, or a receiver that cannot meet its SLA.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-08-18 | **Phases C and D shipped, on the merged tip.** The OLX branch had landed in `origin/dev`, so the branch was rebased first (contingency (a)) and everything after was built on the merged tree. Backend: migration 052, the receiver, four services, the scheduler jobs, the config layer, 109 tests. Frontend: the hook, the health card with its callback-configuration panel, 33 tests. Suites after the rebase: seed 3188/1, MCP 146, product 2092/3, frontend 629, tsc + build — all by exit code. Three LGPD flags recorded via `noctus.dev.lgpd_flag`. Fixed on contact: `KB § PATTERNS/security/webhook-signatures.md` still said "four shapes" after `basic_shared_secret` made it five, and neither portal receiver had registered itself in the adopters list. | tech-lead orchestrator |
| 2026-08-18 | **Gate 0 re-run through the connector, and it settled two questions inference could not.** 0.2 and 0.3 confirmed from the generated spec on both hosts (`configuracao` / `geracao` present, the Spanish spellings absent); every baseline endpoint confirmed to exist; two endpoints the adapter calls added to the baseline; and the vendor's WAF found to 403 `Python-urllib/*` by name. Three new Gate-0 findings recorded (0.11–0.13). | tech-lead orchestrator |
| 2026-08-18 | **Phase B shipped** — `mcp/imovelweb/` with 19 tools, 79 tests green by exit code; `_kit` 31 and the full seed suite 3175/1-skipped re-run clean. Beyond the spec: the integrator-wide `put_config` also refuses a localhost / private / ephemeral-tunnel URL (shared with the future product service via the seed's `receiver_url_problems`), `probe` marks every `/v1/**` row non-discriminating because Gate 0 proved 401-before-routing, and `webhook.simulate` measures our receiver against the vendor's 1.5-second budget locally. Docs synced same commit; **not registered in `.mcp.json`** — the row's `cwd` points at the primary checkout, whose editable `noctusai_lib` has no `integrations.imovelweb` until the merge. | tech-lead orchestrator |
| 2026-08-17 | **Phase A shipped** — the seed package whole (pure half + the Protocol/Fake/Real/factory quartet), 220 tests green by exit code. Two real bugs caught by the tests and fixed in the code (`full_phone` concatenation, a decorative timezone guard); the inbound credential lifted into the seed so connector, receiver and register service cannot drift; and a no-model-on-the-lead-path principle added with a mechanical import test. | tech-lead orchestrator |
| 2026-08-17 | Initial project drafted from `templates/PROJECT-TEMPLATE.md` after interrogation of jraphaelsst (4 decisions in §2). Vendor contract researched from the live OpenNavent Swagger spec + `open-classifieds.notion.site/bra`; recorded in `KB § INTEGRATIONS/imovelweb.md`. **Refutes the OLX project's ImovelWeb-direct hypothesis**: ImovelWeb is Navent/Grupo QuintoAndar, not Grupo OLX, and has its own API, sandbox and callback system. | tech-lead orchestrator |
