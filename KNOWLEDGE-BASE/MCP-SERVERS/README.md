# MCP Servers

> Reference: [02-MCP.md](../INSTRUCTIONS/02-MCP.md) for design patterns and tool documentation best practices.

---

## Built MCP Servers

### github — GitHub connector MCP

**Type**: Connector (composes `mcp/_kit`; wraps the authenticated `gh` CLI)

The **GitHub side of the team methodology** — PR lifecycle + CI-check
visibility + repo introspection — as `github.<service>.<action>` tools.
Raw `git commit`/`git push` are deliberately NOT exposed (they stay in
the commit-only-your-own-work git workflow). Registration is **user-gated**
(MCP keep-list rule). Full reference: [github.md](github.md).

Tools: `github.pr.{list,view,diff,checks,create,ready}` ·
`github.repo.view` · `github.diagnostics.connection_status`. Writes are
confirm-gated (412); `gh` absent/logged-out is a typed never-faked signal.

---

### n8n — self-hosted n8n connector MCP

**Type**: Connector (composes `mcp/_kit`; wraps the n8n public REST API)

The **self-hosted n8n workflow-ops surface** — workflow list/inspect,
execution history, and the full error payload of a failed execution
(the debugging core) — as `n8n.<service>.<action>` tools. Exists
because the `claude.ai`-managed n8n connector can't reach a
self-hosted instance. Secret (API key) lives in the connector's own
`mcp/n8n/.env` (gitignored), not the product/root `.env`. Registration
is **user-gated** (MCP keep-list rule). Full reference: [n8n.md](n8n.md).

Tools: `n8n.workflow.{list,get,activate,deactivate,update,create,
delete,set_tags}` · `n8n.execution.{list,get,delete}` · `n8n.tag.list`
· `n8n.diagnostics.connection_status`. Writes confirm-gated (412);
no-config/unreachable/rejected-key is a typed never-faked signal.
`n8n.workflow.{update,delete}` are hard-to-reverse (get first as a
rollback snapshot). Endpoint surface probed live (variables/projects
403-license-gated + credentials/source-control 404 deliberately not
surfaced). On the keep-list + registered (user-approved 2026-05-19).

---

### waha — WAHA (WhatsApp HTTP API) connector MCP

**Type**: Connector (composes `mcp/_kit`; wraps the WAHA HTTP API)

The **self-hosted WAHA ops surface** — WhatsApp session lifecycle,
messaging, server health, tri-state connection diagnostic — as
`waha.<service>.<action>` tools. Drives the WhatsApp side of n8n flows;
its diagnostic disambiguates the WAHA dashboard's conflated "host down
/ wrong key" error. Secret (`X-Api-Key`) in the connector's own
`mcp/waha/.env` (gitignored). On the keep-list + registered
(user-approved 2026-05-19). Full reference: [waha.md](waha.md).

Tools: `waha.session.{list,get,me,start,stop,restart,logout}` ·
`waha.message.{send_text,list}` · `waha.chat.list` ·
`waha.server.{version,status,ping}` ·
`waha.diagnostics.connection_status`. Writes confirm-gated (412);
`send_text` is the strongest gate (outward-facing, irreversible);
`logout` hard-to-reverse. `server.ping` is unauthenticated.

---

## Planned MCP Servers

### supabase-properties

**Type**: Direct Proxy + Aggregator

Exposes the Supabase ativos (properties) database as MCP tools for AI agents. Enables property search, filtering, and retrieval without direct database access.

**Planned tools:**
- `search_properties` — Filter ativos by type, region, price, specs
- `get_property` — Fetch single ativo by ID with full details
- `list_matches` — Retrieve match results for an ativo

> _`waha-whatsapp` graduated from Planned → Built 2026-05-19 — see the
> **waha** entry under Built MCP Servers above. Future ideas not yet
> built: `send_property_card` (formatted listing send)._

---

### olx — Grupo OLX portal-leads connector MCP

**Type**: Connector (composes `mcp/_kit`; wraps `noctusai_lib.integrations.olx`)

The **Grupo OLX lead pipe** — ZAP · VivaReal · OLX · ImovelWeb · Casa
Mineira, one connector because they share one webhook. Built BEFORE the
product receiver on purpose: the integration is inbound-only with no
sandbox, and OLX discards an undelivered lead after 14 days with no
replay, so a receiver written against unverified prose loses real leads.
The connector's job is to make the contract inspectable, testable,
exercisable and correctable against live behaviour. Secrets in
`mcp/olx/.env` (gitignored). Registration is **user-gated** and must wait
until `feat/olx-portal-leads-mcp` merges. Full reference: [olx.md](olx.md).

Tools: `olx.webhook.{describe_contract,validate_payload,record_delivery,
simulate}` · `olx.contract.diff_observed` · `olx.leads.push` ·
`olx.diagnostics.{connection_status,probe,list_known_endpoints}`. Writes
confirm-gated (412). The contract tools need no credentials at all;
`describe_contract` reports `verified_against_live_traffic: false` until
Gate 1.

---

### imovelweb — ImovelWeb / OpenNavent portal-leads connector MCP *(built; unregistered)*

**Type**: Connector (composes `mcp/_kit`; wraps `noctusai_lib.integrations.imovelweb`)

The **ImovelWeb pipe** — ImovelWeb · Wimoveis · Casa Mineira via OpenNavent
(Navent / Grupo QuintoAndar), a **different vendor from Grupo OLX** even
though the OLX pipe also carries an ImovelWeb bridge. Phase B of
`projects/imovelweb-portal-leads-ingestion/PROJECT.md`; 19 tools live in
`mcp/imovelweb/`, unregistered until the branch merges. Built BEFORE the
product receiver for the same reason
as `olx`, plus two of its own: `PUT /v1/configuracao/callbacks` is
integrator-wide, so one bad call redirects every agency's leads and belongs
behind a confirm-gate with a read-back diff; and unlike OLX there **is** a
sandbox with an event simulator, so the contract is provable before any real
traffic. The vendor allows 1.5 s for our response and retries for 72 h before
marking a callback `VENCIDO`. Secrets in `mcp/imovelweb/.env` (gitignored).
Registration is **user-gated** and must wait until
`feat/imovelweb-portal-leads` merges. Full reference: [imovelweb.md](imovelweb.md).

Tools: `imovelweb.contract.{describe,validate_payload,diff_observed}` ·
`imovelweb.callbacks.{get_config,put_config,subscribe,unsubscribe}` ·
`imovelweb.leads.{get_message,list_messages,get_smartlead,list_contact_actions}` ·
`imovelweb.agencies.list` · `imovelweb.sandbox.emit_event` ·
`imovelweb.webhook.{record_delivery,simulate}` ·
`imovelweb.diagnostics.{connection_status,probe,list_known_endpoints,fetch_swagger}`.
Writes confirm-gated (412). `fetch_swagger` exists because this vendor
publishes an unauthenticated OpenAPI spec — the doc-vs-reality loop closes
without waiting for traffic. Contract tools need no credentials;
`describe` reports `verified_against_live_traffic: false` until Gate 1.

---

## Adding a New MCP Server

1. Create a directory: `MCP-SERVERS/{server-name}/`
2. Add `server.py` — MCP server implementation
3. Add `tools.json` — Tool definitions following the template in [07-TEMPLATES.md](../INSTRUCTIONS/07-TEMPLATES.md)
4. Document in this README
5. Add eval cases in `EVALS/cases/`

## Security Checklist

Per [02-MCP.md](../INSTRUCTIONS/02-MCP.md):

- [ ] API keys in environment variables, never hardcoded
- [ ] Rate limiting implemented and documented
- [ ] Input validation on all tool parameters
- [ ] Error handling returns structured errors
- [ ] Timeout handling with configurable timeouts
- [ ] Logging of all invocations (without sensitive data)
- [ ] Auth scope: each server only has access needed
