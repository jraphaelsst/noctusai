# ImovelWeb portal leads — OpenNavent (Navent · Grupo QuintoAndar)

> **Status: TRANSCRIBED, NOT VERIFIED.** Everything below is read off the live
> Swagger 2.0 spec (`api-br-open.navent.com/v2/api-docs?group=opennavent-realestate`,
> version `2.105.01-RC1`) and `open-classifieds.notion.site/bra` on 2026-08-17.
> Nothing has been checked against a live delivery. Treat every statement as a
> hypothesis until the change log (§8) records an observation.
> → `projects/imovelweb-portal-leads/PROJECT.md`
>
> Operations doc (config, registration, tests): `KB § MCP-SERVERS/imovelweb.md`.
> Code: `seed/lib/backend/noctusai_lib/integrations/imovelweb/`, `mcp/imovelweb/`.
>
> **Not Grupo OLX.** ImovelWeb is a Navent brand; QuintoAndar acquired Navent's
> real-estate operations in 2022. Grupo OLX *does* publish an ImovelWeb bridge
> for its Gestor de Leads (`KB § INTEGRATIONS/olx.md` §0), so both pipes can
> carry the same enquiry — see §5 for why that matters.

## 0. The shape, and why it constrains everything

Bidirectional, and that is the whole difference from OLX. ImovelWeb **POSTs one
event per request** at a URL we register — but the registration is an API *we*
call, and there is also a **pull API** and a **sandbox with an event simulator**.

Four consequences that drive every design decision downstream:

1. **The response budget is 1.5 seconds.** Not a soft target: a slower answer is
   scored a timeout, i.e. an error. That rules out org resolution, listing
   lookups, or an authoritative re-fetch inside the request. Persist once,
   answer, process in the background.
2. **A non-2xx costs 72 hours, not the lead.** Retries continue until delivery
   or 72 h elapse, then the callback goes `VENCIDO`. Combined with the pull API
   (§6), a miss is *recoverable* — which is what makes the tight budget
   survivable. Reconciliation, not the webhook, is the durability guarantee.
3. **Silence is the default failure mode.** Registering a URL delivers nothing
   until events are subscribed one at a time. A perfectly-configured receiver
   with an empty `subscriptions` list is the likeliest production incident, and
   it produces no error anywhere.
4. **Duplicates are normal.** Retries plus reconciliation mean the same event
   legitimately arrives more than once, by two different paths. Idempotency on
   `eventId` is a correctness requirement.

**3xx counts as success**, not just 2xx — the vendor is explicit. Never rely on
it; do record it (`IMOVELWEB_RESPONSE_SEMANTICS`).

## 0a. What the spec does and does not tell you (Gate 0, 2026-08-17)

Three facts worth knowing before you plan any verification against this vendor.

1. **The spec models zero callback bodies.** `/v2/api-docs?group=opennavent-realestate`
   is public and complete for the API *we call* — but grepping every definition
   for `eventId` / `idEvento` / `tipoEvento` / `eventType` / `leadOrigin` /
   `originLeadId` / `clientListingId` returns an empty set. The bodies they
   **push** are documented in prose only. So §2's tables cannot be confirmed from
   the machine-readable source, and the language question (§2) is settled by
   *observing an emitted event*, not by reading. This is why `contract.py` is
   language-parameterized rather than pinned: the design has to survive not
   knowing.
2. **`/v1/**` returns 401 before routing.** Spring Security's filter chain runs
   ahead of the dispatcher, so `/v1/definitely-not-a-real-endpoint-xyz` also
   answers 401, while `/nope` — outside the secured pattern — answers 404.
   **An unauthenticated probe cannot tell a real path from a typo.** That retires
   the obvious way to settle the two `configuracao`/`configuracion` and
   `geracao`/`generacion` spellings; the generated spec's spelling is the better
   evidence, since prose is hand-written and the spec is not.
3. **Errors are XML, not JSON.** A 401 answers `Content-Type: application/xml`
   with `<UnauthorizedException><error>unauthorized</error><error_description>An
   Authentication object was not found in the SecurityContext</error_description></UnauthorizedException>`,
   despite the spec declaring `produces: */*`. `real.py` must parse defensively
   and fall back to raw text — otherwise every upstream failure surfaces as a
   JSON decode error instead of the vendor's actual message.

## 1. Authentication — two directions

**Outbound (us → vendor): OAuth2 client credentials.**

```
POST /v1/application/login?grant_type=&client_id=&client_secret=
  → OAuth2AccessToken { value, tokenType, expiresIn, expiration, scope[], refreshToken{…} }
POST /v1/application/logout?client_id=&client_secret=&token=
```

- The documented form puts `client_secret` **in the query string** — into access
  logs, proxies and `str(httpx_exception)`. Gate 0.8 tests whether the endpoint
  also accepts `Authorization: Basic base64(id:secret)` + a form body (Spring
  Security OAuth2 normally does). Prefer that; query params only behind an
  explicit `allow_secret_in_url=True`.
- The vendor's own Swagger UI sends the **token** as `?access_token=`. Prefer
  `Authorization: Bearer` and verify empirically (Gate 1.2).
- Token scope is believed **per-integrator**, with the agency as a path
  parameter — one credential pair, app-wide. **Unverified**; if it turns out to
  be per-agency the whole config layer moves from `app_integration_config` to
  per-org `integration_accounts`.
- `expiresIn` units and `expiration` encoding are **both unverified** (Gate 0.7).
  `_parse_expiry` handles all four shapes and WARNs when it has to guess.
- `logout()` is explicit-only, never a shutdown hook: the MCP connector and the
  backend may share credentials, and one logout revokes the other's token.

**Inbound (vendor → us): the header we chose.** There is no signature. We
register both the header name and its value:

```
authorizationHeaderKey   = "Authorization"
authorizationHeaderValue = "Basic " + base64("noctusai-imovelweb:<secret>")
```

Consumed by `webhook_endpoint(scheme="basic_shared_secret",
basic_username="noctusai-imovelweb")` — the same scheme Grupo OLX forced on us,
reused rather than adding a sixth. **Same weakness, same obligations**: the
header is identical on every request, binds nothing, and is replayable forever
by anyone who captures one. TLS on the endpoint and idempotency on `eventId` are
not optional. Unlike OLX we can also re-fetch by `messageId`, so the body is a
**hint**, not truth, for anything that matters.

## 2. Payload

Source of truth is `noctusai_lib/integrations/imovelweb/contract.py` — this
section is a reading aid, not a second copy. `imovelweb.contract.describe`
serves the live version.

**The contract is language-parameterized.** `lenguajeCallbackBody` ∈
`EN | EN2 | EN_SF | ES | PT` changes the field *names*, not just the copy. That
is the one structural divergence from every other integration we run.

### 🔴 The language trade-off — Gate 0.4, and it reshapes the code

No variant documented by the vendor carries both fields we need:

| Variant | Agency code (tenant resolution) | `leadOrigin` (portal attribution) |
|---|---|---|
| `PT` | ✅ `codigoImobiliaria` | ❌ absent |
| `ES` | ✅ `codigoCliente` | ❌ absent |
| `EN` | ✅ `clientCode` | ❌ absent |
| `EN2` | ❌ absent from the sample | ✅ `leadOrigin` |
| `EN_SF` | ❌ | ❌ (flat `{token,id,txtNome,txtEmail,txtDdd,txtTelefone,messageId,txtMensagem}`) |

`EN2` is otherwise the obvious pick — it is near field-identical to the Grupo OLX
payload we already model, which is *why* the enum has an "EN2" at all. But the
vendor's own shared field-description list *does* name
"codigoImobiliaria, codigoInmobiliaria e clientCode" for this event, so the
omission may be a doc error. **Read the model out of the live spec and settle it
before writing the parser** — the answer decides `contract.py`, `webhook.py`, the
tenant-resolution chain (§4) and the migration column set. If `EN2` really omits
the agency code, **`PT` is correct for a multi-tenant receiver** and attribution
falls back to `clientListingId → imoveis → org`.

### `CONTACTO_MENSAJE` — EN2

| Field | Type | Notes |
|---|---|---|
| `eventId` | string | Per-**delivery** id. **THE dedup key**, and the vendor's own advice. |
| `eventType` | string | `CONTACTO_MENSAJE` |
| `contactTypeId` | int | §2.1 |
| `timestamp` | string | `yyyy-MM-dd'T'HH:mm:ss.SSSZ` — Java `Z` is an RFC-822 **numeric offset** (`-0300`), not the literal character. |
| `name` `email` `ddd` `phone` `phoneNumber` | string | Consumer PII. `phone` is international with a leading `+`; `phoneNumber` = ddd+phone; **either may be empty**. |
| `message` | string | Consumer message. |
| `messageId` | long | Navent message id — the re-fetch handle for `GET /v1/mensagens/{id}`. |
| `originLeadId` | int | Navent **contact** id. One contact fans out to several events. Omitted when null. |
| `originListingId` | long | Their listing id. |
| `clientListingId` / `reference` | string | **Our** listing code. Omitted if never associated. |
| `internalReference` | string | The code the imobiliária uses in the vendor's panel. |
| `leadOrigin` | string | `Imovelweb` · `Wimoveis` · `CasaMineira`. |
| `idNavplatDevelopment` `developmentCode` | long/string | Parent development; omitted when not a development or unit. |
| `userIdNavplat` | string | Masked seeker id, vendor-internal. |
| `identificationId` | string | **CPF.** See §2.2. |

`CONTACTO` (phone-reveal) is the same minus `messageId`/`message`, and may omit
`name`.

**The parser tolerates the unexpected.** A 4xx on an unknown enum or an
unrecognised language starts a 72-hour retry loop against a body that will never
change. `parse_imovelweb_callback` returns `None` only when there is no event id
— no dedup key means the event is unstorable.

### 2.1 `contactTypeId`

`1` CONSULTA · `2` QUE_ME_LLAMEN · `3` AGENDAR_VISITA · `6` DATOS_ANUNCIANTE ·
`10` DATOS_ANUNCIANTE_WHATSAPP · `12` TASACION · `15` AGENDAR_VISITA_CRONUT.

Transcribed. `GET /v1/contatos/acoes` is the authoritative catalog and replaces
this table at Gate 1.11.

### 2.2 `identificationId` is a CPF

A direct national identifier — the highest-value PII in the leads pipeline, and
a class the Grupo OLX payload does not carry. **It is deliberately not projected
and not stored in a typed column.** It still arrives inside the lossless `raw` /
`payload` JSONB, which makes those two columns CPF-bearing and means neither may
ever be selected into a response. → `KB § PATTERNS/security/lgpd.md`.

## 3. Response contract — the refusal we do NOT make

| Our status | What ImovelWeb does |
|---|---|
| 2xx **or 3xx** | Delivered. Never sent again. |
| anything else | Failure. Retry until delivered or 72 h → `VENCIDO`. |
| no answer in **1.5 s** | Scored a timeout, i.e. a failure. |

**We answer 200 for a listing lead with no `clientListingId`.** This is the
deliberate inversion of the OLX receiver, which 4xxs that exact case. OLX
documents a requeue path for it; ImovelWeb does not, and the field is
legitimately absent when the listing was never associated — so a 4xx would
requeue for 72 hours a field that will never arrive.

**We answer 5xx when our own durable write fails.** The one place a non-2xx is
correct: the vendor retries for 72 h and we hold a pull API, so a 5xx is
strictly better than a 200 that loses the lead. Do not "fix" this to a 200.

## 4. Tenant resolution

Chain, in order, never guessing:

1. `codigoImobiliaria` → `imovelweb_agencies.org_id`. **We choose the agency
   code** at onboarding (§7), so this is a pure lookup — a real improvement over
   the OLX pipe. Available only if the chosen language carries the field (§2).
2. `clientListingId` / `reference` → `imoveis.codigo` → `org_id`.
3. `internalReference` → `imoveis.codigo` — secondary; it is the vendor-panel
   code, which may not be ours.
4. a configured single org (`imovelweb_leads_org_id`);
5. otherwise park the event as `unresolved`, `org_id NULL`, and write nothing.

Step 5 is the tenant-leak guard, and mirrors both the Meta receiver's unknown
`page_id` and the OLX receiver's unresolved branch.

## 5. Attribution

**Separate the idempotency key from the attribution slug.** OLX conflated them;
here that would be a duplication bug.

- `leads.external_source` is the **constant `imovelweb`** — the *pipe*, and half
  of `uq_sw_leads_org_external_lead`. If it varied with `leadOrigin`, the same
  `eventId` re-delivered with a changed or absent `leadOrigin` would silently
  insert a second row.
- `leads.origem_id` is the per-portal `lead_sources` row: `imovel-web` or
  `casa-mineira`, from `leadOrigin`. Per-portal attribution is **honest here**,
  unlike the OLX pipe where the payload never names the portal.

`wimoveis` has no `lead_sources` slug and no observed BR traffic. It falls back
to `imovel-web` with the true value preserved in `origem_raw`. Do not mint a slug
for a value nobody has seen.

**Cross-pipe duplicates.** An advertiser activated on *both* Gestor de Leads and
our direct callback receives each enquiry twice, under two different vendor ids
(`originLeadId` on the OLX pipe, `eventId` here). `uq_sw_leads_org_external_lead`
will **not** catch it, because `external_source` differs. Do not paper over this
with a fuzzy key: it is a Gate 2 question to the advertiser, and at most an
advisory duplicate-suspect count on `(email|phone, listing, ±30 min)` in the
health card. Never auto-merge.

## 6. Endpoint inventory

Legend: ✅ live-200 · 🔒 live-401 · ❌ live-404 · 📖 doc-only · ❓ referenced ·
**⏳ unverified** (documented, never probed).

| Path | Status | Wrapped by |
|---|---|---|
| `POST /v1/application/login` · `/logout` | ⏳ | `auth.py` |
| `GET` / `PUT /v1/configuracao/callbacks` | ⏳ | `imovelweb.callbacks.get_config` / `.put_config` |
| `PUT` / `DELETE /v1/configuracao/callbacks/{evento}` | ⏳ | `imovelweb.callbacks.subscribe` / `.unsubscribe` |
| `POST /v1/callbacks/geracao/eventos` (**sandbox only**) | ⏳ | `imovelweb.sandbox.emit_event` |
| `GET /v2/imobiliarias/{cod}/mensagens` | ⏳ | `imovelweb.leads.list_messages` |
| `GET /v1/mensagens/{idMensaje}` | ⏳ | `imovelweb.leads.get_message` |
| `GET /v1/mensagen/{id}/smartLead` | ⏳ | `imovelweb.leads.get_smartlead` |
| `GET /v1/imobiliarias/{cod}/contatos/{idContato}` | ⏳ | `imovelweb.leads.get_contact` |
| `GET /v1/seekers/br/{userIdNavplat}/profile` | ⏳ | `imovelweb.leads.get_seeker_profile` |
| `GET /v1/contatos/acoes` | ⏳ | `imovelweb.leads.list_contact_actions` |
| `GET /v1/imobiliarias` · `DELETE /v1/imobiliarias/{cod}/` | ⏳ | `imovelweb.agencies.list` / `.unlink` |
| `GET /v2/api-docs?group=opennavent-realestate` (**public, no auth**) | ⏳ | `imovelweb.diagnostics.fetch_swagger` |
| our receiver (inbound) | n/a | `imovelweb.webhook.simulate` |

Every row is ⏳ on purpose. `IMOVELWEB_ENDPOINT_BASELINE` records `None` as the
expected status rather than a guess: a guessed expectation makes the probe print
`as_expected` for a number we invented, and an operator who learns the report
lies stops reading it.

**Two path spellings are unresolved**, and `IMOVELWEB_PATH_VARIANTS` carries both
rather than picking one: the docs write `/v1/configuracion/callbacks` (Spanish)
where the live BR spec says `/v1/configuracao/callbacks`, and the docs name the
simulator `/v1/callbacks/generacion/evento` where the spec says
`/v1/callbacks/geracao/eventos`.

**Hosts.** Prod BR `api-br-open.navent.com` · sandbox BR
`api-br-sandbox-open.navent.com` (**up only ~07:00–21:00 UTC-3**) ·
`api-zp-open.navent.com` (AR) · `api-rela-open.navent.com` (rest of LatAm).

## 7. Adapter contract

- **Parse** `parse_imovelweb_callback(payload, *, language=None) -> ImovelWebLead | None`
  — pure, zero IO, never raises. `detect_callback_language` scores the body's
  keys when the language is not pinned.
- **Validate** `validate_imovelweb_payload(payload, *, language)` — splits
  `error` from `warning` so §3's single-refusal line stays drawn.
- **Map** `imovelweb_lead_to_lead_payload(...)` — raises rather than inventing a
  `data_entrada`, and **never assigns a corretor**. Timestamps convert through
  the payload's own offset, falling back to `America/Sao_Paulo`, never to UTC: a
  21:30 BRT lead is the *previous* day in UTC, and that error lands straight in
  Portal ROI.
- **Configure callbacks** `get_callback_config` / `put_callback_config` /
  `subscribe_event` / `unsubscribe_event`. ⚠️ **`PUT /callbacks` is
  integrator-wide** — there is no agency in the path, so one bad PUT redirects
  every agency's leads. It is confirm-gated in the MCP, an explicit admin action
  in the product (never a startup hook, never the scheduler), and always read
  back and diffed. The register path refuses a localhost, private-range or
  ephemeral-tunnel URL, because such a registration blackholes production leads
  with no error anywhere.
- **Reconcile** `list_agency_messages` / `get_message` — the poll-side safety net
  for the 72 h expiry, hourly with a 7-day lookback. ⚠️ The reconcile response is
  a `Mensaje` (`{id, idMensaje, idContacto, …}`) and carries **no `eventId`**; how
  its ids relate to the callback's `eventId` / `messageId` is a Gate blocker,
  because getting it wrong duplicates every lead.
- **Enrich** `get_smartlead` / `get_contact` / `get_seeker_profile` — buyer
  intent, fetched in the background, never in the request path.
- **Onboard** the vendor's login button: `<div id="opennavent"></div>` plus
  `https://loginbr-open.navent.com/[INTEGRADOR]/[CODIGOIMOBILIARIA].js`. The
  imobiliária self-authorizes and **we pick `CODIGOIMOBILIARIA`**, which is what
  makes §4 step 1 a pure lookup.
- **Errors** `ImovelWebConfigError` → HTTP **424** (gated-capability honesty:
  "not configured" ≠ "outage"); `ImovelWebUpstreamError` → the vendor's status,
  else 502. `redact_secrets` runs at every boundary over **three** secrets —
  `client_secret`, the bearer token, and the callback header value — because an
  MCP tool result goes straight into a model's context window.

## 8. Change log

| Date | What changed | Evidence |
|---|---|---|
| 2026-08-17 | Doc transcribed from the live Swagger spec + vendor docs. | spec JSON + vendor HTML |
| 2026-08-17 | **Gate 0 ran.** Prod spec `2.105.01-RC1`, sandbox `ON-10172`; identical path sets except the sandbox-only `POST /v1/callbacks/geracao/eventos`. `OAuth2AccessToken.expiration` is ISO `date-time`, `expiresIn` is int32 seconds, `refreshToken` has no expiry of its own. `ConfiguracionCallback` carries `subscriptions[]`, so one `PUT` sets everything atomically. | both specs downloaded |
| 2026-08-17 | **Two structural findings — see §0a.** The spec models zero callback bodies, and `/v1/**` 401s before routing. | live probes |

> **Fill this in at Gates 0/1/2.** `imovelweb.contract.diff_observed` and
> `imovelweb.diagnostics.fetch_swagger` produce the input; record the observation
> *and* the date, then flip the `verified` flags in `contract.py`.

## 9. Getting unblocked

| Need | Contact |
|---|---|
| Sandbox credentials, production credentials, callback config by email | `integracao@imovelweb.com.br` |
| Platform/API contact of record (from the spec) | `open@navent.com` |
| Integration tickets | `navent.atlassian.net/servicedesk/customer/portal/9` |
| ImovelWeb → Grupo OLX Gestor de Leads activation (the *other* pipe) | `atendimento@imovelweb.com.br` |

**Unlike Grupo OLX there is a real sandbox**, and it ships an event simulator
(`POST /v1/callbacks/geracao/eventos`) that pushes a synthetic `CONTACTO` /
`CONTACTO_MENSAJE` at our registered URL. That is why the contract can be proven
before a single real lead exists — the gate the OLX project could not close.
Agency and listing codes must be real in sandbox; `CONTACTO_MENSAJE` requires
name + phone + email + message, `CONTACTO` only email.

## 10. Reference

Docs · spec · login-button · support — the exact URLs live in
`noctusai_lib/integrations/imovelweb/endpoints.py::IMOVELWEB_REFERENCE_URLS` and
`::IMOVELWEB_SUPPORT_CONTACTS`, so an agent gets them from the tool rather than
from this page. Docs root: `open-classifieds.notion.site/bra`
(`open-docs.navent.com/bra` 301s there). The spec is public and unauthenticated,
which is what makes `imovelweb.diagnostics.fetch_swagger` possible.
