# Automation candidates

Ideas for automations the owner wants, each tied to what is actually known today. None is
built. Before building any, settle the two blockers below.

## Blockers (settle first)

1. **Access path.** Two options, both unverified:
   - **Browser-driven** (Chrome MCP, the user's logged-in session): works today for reads,
     per `playbook/browser.md`, but it's slow (~10s/page) and needs the user's browser.
   - **API client** against `apigw.prod.quintoandar.com.br`: faster, but the auth scheme is
     unknown (`knowledge/api.md`), and whether QuintoAndar permits programmatic access to
     the partner portal is not established. Ask the owner before inspecting auth or calling
     the API outside the browser.
2. **Writes.** No write endpoint or write effect is known. Any automation that confirms,
   cancels, edits or shares something needs that action first tested manually, with
   per-action consent, and documented in `knowledge/api.md`.

## Repo conventions that apply when building

- New automation = an MCP tool / server, not a loose script (CLAUDE.md "MCP-first
  scripts"). Precedents for vendor servers: `mcp/vista`, `mcp/olx`, `mcp/imovelweb`,
  `mcp/waha`. Seed-side integrations live in `seed/lib/backend/noctusai_lib/integrations/`
  (vista, olx, imovelweb, whatsapp…). Check `noc-verify-seed` / `noc-mcp-tool` skills
  before starting. A QuintoAndar integration would be seed-first: Fake + Real + factory.
- LGPD: outputs carry owner/lead personal data — follow the repo's LGPD patterns.
- Self-branch before writing anything (repo rule).

## Candidates (read-only first)

| # | Automation | Data source (observed) | Needs a write? | Notes |
|---|---|---|---|---|
| 1 | **Daily "visits to confirm" digest** — unconfirmed visits with date/time, property, broker, and the auto-cancel deadline | `listing-visits/list` (status REQUESTED — name-based mapping, verify); deadline text in the "Confirmar visita" drawer | No (digest). Confirming from the digest = yes | Delivery channel could reuse the repo's WhatsApp/WAHA integration — decide with owner |
| 2 | **Pendências → CRM fix list** — the "Imóveis com pendência" list grouped by reason, one to-do per property, for fixing in Vista | `property-listing/search` (has a `groupName` param; its value for the pending list not captured) or `/status/pending` scrape | No | Pairs with the Vista MCP (`mcp/vista`) and the memory on Vista data conventions for QuintoAndar "Correção de Dados" reports |
| 3 | **Portfolio status snapshot** — daily counters per status, trend over time | `property-listing/counters` (total, count{}) | No | Would also make the "Todos os imóveis" divergence visible over time |
| 4 | **Deactivation/ineligibility reasons report** — full motivo breakdown | `/status/unpublished`, `/status/notEligible` lists | No | Full lists are large (hundreds/thousands); use perPage=10 in browser mode (freeze at 30) |
| 5 | **Low-performance listings brief** — score, current vs suggested value, views/visits last 30 days | `listing-performance/listings`; report-setup page | No (brief). Changing price / sharing report = yes | Report share uses a `quin.to` short link + WhatsApp button — effects untested |
| 6 | **Photo sessions to schedule** — properties "Agendamento pendente" | `listing-photo-session/list` (page, perPage seen; how the "Para agendar" filter — URL `status=PENDING` — reaches the API not captured) | No (list). Scheduling = yes | `/photos` has no menu link — confirm the owner uses it |
| 7 | **Visit-hours audit** — properties whose availability excludes high-demand ("Alta Procura") slots | `property-overview/:id/visit-availability` | No | Only the modal showed "Alta Procura" tags; whether the API carries that flag is unverified |

Pick one with the owner, then: verify access path → prototype read-only → confirm output
with the owner → only then consider write steps.
