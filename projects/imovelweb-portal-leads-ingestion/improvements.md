# Improvements — ImovelWeb portal-leads ingestion (OpenNavent) — Project Document

> **Auto-generated** from `PROJECT.md` by `python mcp/noctusai/cli.py --improvements <plan.md>`. Regenerated every time a phase is ticked complete. Do not edit by hand.

> This file captures **improvement opportunities discovered while implementing each phase** — things future iterations of *this* phase should consider. It is NOT a preview of upcoming phase tasks (those live in the plan itself). When a phase is refactored or revisited, open this file first.

**Plan:** `PROJECT.md`
**Plan status:** 🅿️ Design locked → Gate 0 ready (Gate 0 needs no credentials — start there)
**Completed phases:** 0 of 0.
**Phases with recorded improvements:** 0 of 0 completed.

## Improvements by phase

_No improvements recorded yet. As each phase completes, the agent should append an `**Improvements:**` block to that phase section in the plan, then re-run this tool._

## Deferred items (from §4 Out of scope)

_Work deliberately scoped out of this plan. Track as candidates for future plans, not as improvements to existing phases._

- **Listing events (`AVISO_ACTIVIDAD` / `AVISO_ESTADO_PUBLICACION` /
- **A shared `portal_lead` normalization primitive across OLX + ImovelWeb** —
- **Outbound listing publication to ImovelWeb** — a different direction and a
- **Cross-pipe deduplication against Gestor de Leads** — advisory count only.
- **A `wimoveis` `lead_sources` slug** — no observed BR traffic. §7 Q6.

## Open questions still blocking

- **`AVISO_*` scope** — read/write credentials are required to receive listing
- **Do we store the CPF at all?** *Needs an answer before Phase C's migration.
- **Is any advertiser also live on the Grupo OLX pipe for ImovelWeb?** *Needs an
- **`codigoImobiliaria` derived from the org, or whatever the agency already
- **`imovelweb_lead_events` / `imovelweb_leads` retention TTL — what N?** *Needs
- **A `wimoveis` `lead_sources` slug now, or fold into `imovel-web`?**
- **Will the OLX branch merge?** *Flips §8's contingency from (a) to (b) and adds
- Rate limits — undocumented. What is the ceiling for
- Is the OAuth token scoped to the integrator or to an agency? Can one token
- Token lifetime; is `refreshToken` usable, or is re-login the intended path?
- Callback config is integrator-wide — is a **per-agency** callback URL
- `clientListingId` — the docs contradict themselves: omitted when the listing
- `configuracao` vs `configuracion` — which is live on the BR host, and is the
- Simulator path — `geracao/eventos` or `generacion/evento`?
- `Mensaje.id` / `idMensaje` vs the callback's `eventId` / `messageId` — same id
- Does the vendor deliver from a fixed IP range? *(Would let us add an
- Is there a delivery-status API (which events are `VENCIDO`) so losses are
- **EN2 vs PT** — which is recommended for a multi-tenant integrator, and does
