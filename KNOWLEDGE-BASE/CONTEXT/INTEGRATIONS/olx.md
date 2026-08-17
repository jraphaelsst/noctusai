# Grupo OLX portal leads (ZAP · VivaReal · OLX · ImovelWeb · Casa Mineira)

> **Status: TRANSCRIBED, NOT VERIFIED.** Everything below is read off
> `developers.grupozap.com` on 2026-08-17. Nothing here has been checked
> against a live delivery. Treat every statement as a hypothesis until the
> change log (§8) records an observation. → `projects/olx-portal-leads-ingestion/PROJECT.md`
>
> Operations doc (config, registration, tests): `KB § MCP-SERVERS/olx.md`.
> Code: `seed/lib/backend/noctusai_lib/integrations/olx/`, `mcp/olx/`.

## 0. The shape, and why it constrains everything

The lead integration is **inbound-only**. OLX POSTs **one lead per request** at
a URL we register with them. There is no pull API, no batch endpoint, and **no
sandbox**.

Three consequences that drive every design decision downstream:

1. **Only our status code is read.** The vendor is explicit: *"Use apenas o
   código HTTP para definir o resultado da entrega. Não confie no conteúdo do
   corpo da resposta."* A 200 with an error body means "delivered, done".
2. **A non-2xx costs the lead.** 3 retries, then a 14-day store, then permanent
   discard. There is no replay API. So every "reject it to be safe" instinct is
   really "throw a real customer away", and the code refuses exactly one thing
   (§3).
3. **Duplicates are normal, not exceptional.** Retries plus store-and-forward
   mean the same `originLeadId` legitimately arrives more than once.
   Idempotency is a correctness requirement, not a nicety.

One pipe carries every Grupo OLX portal. ImovelWeb and Casa Mineira join it
once the advertiser emails `atendimento@imovelweb.com.br` for an activation
code and registers it in Gestor de Leads — **unverified**, and item 4 of Gate 1.

> **Qualified 2026-08-17.** The *bridge* above is real —
> `developers.grupozap.com/leadManager/imovelweb_casamineira` documents it. The
> **vendor-identity framing is not**: ImovelWeb and Casa Mineira are not Grupo
> OLX properties. ImovelWeb is a Navent brand, and QuintoAndar acquired Navent's
> real-estate operations in 2022; it runs its own API, sandbox and callback
> system (`KB § INTEGRATIONS/imovelweb.md`). The title of this page and the
> package docstrings still read as if the five portals were one vendor — they
> are one *pipe*, which is a different claim. Two consequences:
> 1. Leads reaching us through this bridge arrive as `leadOrigin: "Grupo OLX"`
>    and are **not portal-attributable**. The direct ImovelWeb integration is the
>    one that names the portal.
> 2. An advertiser activated on **both** pipes sends each enquiry twice, under
>    two different vendor ids (`originLeadId` here, `eventId` there), which
>    `uq_sw_leads_org_external_lead` will not catch because `external_source`
>    differs. → `projects/imovelweb-portal-leads-ingestion/PROJECT.md` §5.
>
> The remaining docstring/title corrections are tracked as Phase A0 of that
> project rather than applied here, because this branch is stacked on a live
> `feat/olx-portal-leads-mcp` and those files are still being edited there.

## 1. Authentication

**HTTP Basic**, no signature, no timestamp:

```
Authorization: Basic base64("vivareal:<SECRET_KEY>")
```

- The username half is the literal `vivareal` — the company rebranded to Grupo
  OLX, the credential did not. `GRUPO_OLX_BASIC_USERNAME` in
  `noctusai_lib.security.webhook_signatures`; `expected_username=None` disables
  the check so a rebrand cannot lock us out.
- `SECRET_KEY` is **per CRM, not per advertiser**. It authenticates *Grupo OLX*
  to us; it does not identify which client the lead belongs to (§4).
- **This is the weakest scheme the platform speaks.** The header is identical
  on every request: it does not bind the body, and it is replayable forever by
  anyone who captures one request. Two obligations follow, neither enforceable
  by the verifier itself — TLS on the endpoint, and idempotency on
  `originLeadId` so a replay is a no-op.

Verifier: `verify_basic_shared_secret` / `webhook_endpoint(scheme="basic_shared_secret")`.

Outbound (Gestor de Leads) is different: `X-API-KEY` + `X-Agent-Name` headers.

## 2. Payload

Source of truth is `noctusai_lib/integrations/olx/contract.py` — this table is
a reading aid, not a second copy. `olx.webhook.describe_contract` serves the
live version.

| Field | Type | Required | Notes |
|---|---|---|---|
| `leadOrigin` | string | ✅ | `Grupo OLX` or `MCMV_OLX`. **Does not name the portal.** |
| `timestamp` | string | ✅ | ISO-8601. |
| `originLeadId` | string | ✅ | Vendor lead id. THE dedup key. |
| `originListingId` | string | ⛔ MCMV | Their listing id. |
| `clientListingId` | string | ⛔ MCMV | **Our** listing id, as published in the feed. |
| `name` `email` `ddd` `phone` | string | ✅ | Consumer PII. |
| `phoneNumber` | string | — | Full phone. Marked deprecated, still sent. |
| `message` | string | ✅ | Consumer message. |
| `temperature` | string | ✅ | `Baixa` · `Média` · `Alta`. |
| `transactionType` | string | ✅ | `RENT` · `SELL`. |
| `extraData` | object | ✅ | `leadCerto` · `izi` · `feedback` · `leadType` · `mcmv`. |

`extraData.leadType` ∈ `CLICK_SCHEDULE` · `CLICK_WHATSAPP` · `CONTACT_CHAT` ·
`CONTACT_FORM` · `PHONE_VIEW` · `VISIT_REQUEST`.

**MCMV leads** (Minha Casa Minha Vida simulations) carry neither listing id.
That absence is correct for them, so 4xx-ing one would requeue a lead the
vendor will never enrich.

## 3. Response contract — the one refusal

| Our status | What OLX does |
|---|---|
| 2xx | Delivered. Never sent again. |
| anything else | Failure. 3 retries → 14-day store → discard. |

We answer **4xx for exactly one condition**: a *listing* lead with no
`clientListingId`, which is the vendor's own documented requeue path. Every
other complaint — unknown `leadType`, unknown `temperature`, an undocumented
field — is a `warning` and still gets a 2xx. `validate_olx_lead_payload` splits
`error` from `warning` precisely to keep that line drawn.

## 4. Tenant resolution (open — Gate 1 item 2)

One secret and (probably) one endpoint for the whole CRM means the payload has
to tell us which org a lead belongs to. Chain, in order, never guessing:

1. path-scoped org token, **if** OLX registers a per-advertiser URL for us;
2. `clientListingId` → `imoveis.codigo` → `org_id`;
3. a configured single org (`OLX_LEADS_ORG_ID`);
4. otherwise park the event as `unresolved` and write nothing.

Step 4 is the tenant-leak guard, and mirrors what the Meta receiver does with
an unrecognised `page_id`.

## 5. Attribution

**One canonical source slug today: `grupo-olx`.** The payload does not name the
portal, so writing `zap` / `viva-real` / `imovel-web` per lead would be a guess
recorded in Portal ROI as if it were data. `origem_raw` keeps
`leadOrigin / leadType` so the discriminator is recoverable later.

**The splitter seam is built and wired; its rule table is empty.**
`noctusai_lib.integrations.olx.portal_split` sits on the ingest path already
(`olx_ingest_service.ingest_olx_lead` → `resolve_portal_source_slug` →
`get_or_create_olx_source(slug)`), and returns the `grupo-olx` umbrella for
every lead because `OLX_PORTAL_RULES` is `()`. That is the honest answer, and
it makes the Gate-1 split a **data** change:

```python
PortalRule(
    slug="zap",                      # must be a real lead_sources slug
    field="extraData.sourcePortal",  # raw body first (dotted), then OlxLead attr
    equals="ZAP",                    # or contains=… (case-insensitive)
    evidence="delivery 4f21c…, 2026-09-02, extraData.sourcePortal='ZAP'",
)
```

Two refusals are enforced at construction, because both failure modes end as
permanent, wrong Portal ROI attribution that nothing downstream can distinguish
from a fact:

- **`evidence` is required and must be an OBSERVATION** — which delivery, when,
  what the field held. "The docs imply it" does not qualify.
- **`slug` must be one of the canonical portal slugs** (`zap`, `viva-real`,
  `imovel-web`, `olx`, `casa-mineira`, `grupo-olx`). They already exist in
  `seed_data.CANONICAL_SOURCES`, so a split needs no migration; an unknown slug
  would drop the lead out of Portal ROI entirely.

**`leads.external_source` stays `grupo-olx` even after a split.** It names the
PIPE the lead arrived on and is the dedup namespace for
`uq_sw_leads_org_external_lead` — keying it on the split slug would let one
vendor lead land twice the day a rule changes.

`MCMV_OLX` is **not** a portal (it is the Minha-Casa-Minha-Vida program) and
must not become a rule; there is a regression test pinning that.

## 6. Endpoint inventory

Legend: ✅ live-200 · 🔒 live-401 · ❌ live-404 · 📖 doc-only · ❓ referenced ·
**⏳ unverified** (documented, never probed).

| Path | Status | Wrapped by |
|---|---|---|
| `POST /v1/addLeads` (`crm-leadmanager-leadreceiver-api.olx.com.br`) | ⏳ | `olx.leads.push` |
| our receiver (inbound) | n/a | `olx.webhook.simulate` |

Every row is ⏳ on purpose. `OLX_ENDPOINT_BASELINE` records `None` as the
expected status rather than a guess: a guessed expectation makes the probe
print `as_expected` for a number we invented, and an operator who learns the
report lies stops reading it.

## 7. Adapter contract

- **Parse** `parse_olx_lead_webhook(payload) -> OlxLead | None` — pure, zero
  IO. `None` only when there is no `originLeadId`. Accepts unknown enum values
  (see §3).
- **Validate** `validate_olx_lead_payload`, `has_blocking_violation`,
  `missing_client_listing_id`.
- **Map** `olx_lead_to_lead_payload(...)` — raises rather than inventing a
  `data_entrada`, and **never assigns a corretor**: the payload has no broker
  field, and guessing hands a real customer to the wrong person.
- **Push** `OlxLeadManagerAdapter` + Fake + Real + `make_olx_lead_manager_client`.
  Its `BusinessType` is `SALE`/`RENTAL` — **not** the inbound `SELL`/`RENT`.
  The vendor is inconsistent across its own two surfaces; both the real client
  and the Fake reject the wrong vocabulary loudly rather than passing it on.

## 8. Change log

| Date | What changed | Evidence |
|---|---|---|
| 2026-08-17 | Doc transcribed; seed package + `mcp/olx` built. Nothing probed. | vendor HTML only |

> **Fill this in at Gate 1.** `olx.contract.diff_observed` produces the input;
> record the observation *and* the date, then flip the `verified` flags in
> `contract.py`.

## 9. Getting unblocked

| Need | Contact |
|---|---|
| Lead-integration setup, SECRET_KEY, homologation | `integracaoleads@grupozap.com` |
| Integration tickets | `chamado.integracao@olxbr.com` |
| ImovelWeb → Gestor de Leads activation code | `atendimento@imovelweb.com.br` |

The closest thing to a sandbox is the vendor's **beta endpoint validator**
(`developers.grupozap.com/webhooks/endpoint_validator/`): give it a URL, a
token and a sample body and it reports the status code your endpoint returned.
`olx.webhook.simulate` is our local equivalent, and works without them.

## 10. Reference

Contract · security · validator · Lead Manager API · ImovelWeb — all under
`developers.grupozap.com`; the exact URLs are in
`noctusai_lib/integrations/olx/endpoints.py::OLX_REFERENCE_URLS`, so an agent
gets them from the tool rather than from this page. Reference samples:
`github.com/olxbr/crm-lead-integration`.
