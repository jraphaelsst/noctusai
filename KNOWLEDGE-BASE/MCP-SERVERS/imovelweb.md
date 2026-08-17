# `imovelweb` MCP server — ImovelWeb / OpenNavent portal leads (operations)

> **🚧 NOT BUILT YET.** This is the specification the connector is built to —
> Phase B of `projects/imovelweb-portal-leads-ingestion/PROJECT.md`. Nothing in
> `mcp/imovelweb/` exists on `dev`. The doc lands ahead of the code on purpose:
> the connector is a **prerequisite gate**, so its surface is agreed before it is
> written, and the pointer from `KB § INTEGRATIONS/imovelweb.md` resolves.
>
> Spec + wire detail live in `KB § CONTEXT/INTEGRATIONS/imovelweb.md`. This is
> the operations doc: what the connector is for, its tool surface, config, and
> how to register it.

## Why it exists

`products/social-wiring` is acquiring its third automated lead channel — Meta
Lead Ads, then Grupo OLX (`KB § MCP-SERVERS/olx.md`), now **ImovelWeb ·
Wimoveis · Casa Mineira** via OpenNavent (Navent / Grupo QuintoAndar — **not**
Grupo OLX, despite the OLX pipe also carrying an ImovelWeb bridge).

The OLX connector was built before its receiver to make an unverifiable contract
*inspectable*. Every argument for that applies more strongly here, and two are
new:

1. **`PUT /v1/configuracao/callbacks` is integrator-wide.** There is no agency in
   the path, so one bad call redirects every agency's leads. A confirm-gated
   agent tool that echoes a read-back diff is exactly where that gate belongs.
2. **There is a real sandbox with an event simulator.** OLX offered neither, so
   its Gate 1 could not close without production traffic. Here
   `imovelweb.sandbox.emit_event` pushes a synthetic `CONTACTO_MENSAJE` at our
   own receiver — the contract is provable before a single real lead exists.
   That is why the project's waves put the product slice *after* Gate 1 instead
   of after production credentials.

The constraint that shapes everything: ImovelWeb allows **1.5 seconds** for our
response, retries a failure until 72 hours have passed, then marks the callback
`VENCIDO`. A receiver written against unverified prose either loses leads or
duplicates them.

## Tool surface — ~16 tools

| Tool | Kind | REST / effect |
|---|---|---|
| `imovelweb.contract.describe` | READ | none (zero IO) — takes a `language` |
| `imovelweb.contract.validate_payload` | READ | none (zero IO) |
| `imovelweb.contract.diff_observed` | READ | reads the local corpus |
| `imovelweb.diagnostics.list_known_endpoints` | READ | none (zero IO) |
| `imovelweb.diagnostics.connection_status` | READ | none — **zero API calls** |
| `imovelweb.diagnostics.probe` | READ | bare request per baseline row |
| `imovelweb.diagnostics.fetch_swagger` | READ | `GET /v2/api-docs?group=opennavent-realestate` on **both** hosts, diffed against `endpoints.py` |
| `imovelweb.callbacks.get_config` | READ | `GET /v1/configuracao/callbacks` |
| `imovelweb.agencies.list` | READ | `GET /v1/imobiliarias` |
| `imovelweb.leads.get_message` | READ | `GET /v1/mensagens/{id}` |
| `imovelweb.leads.list_messages` | READ | `GET /v2/imobiliarias/{cod}/mensagens` |
| `imovelweb.leads.get_smartlead` | READ | `GET /v1/mensagen/{id}/smartLead` |
| `imovelweb.leads.list_contact_actions` | READ | `GET /v1/contatos/acoes` |
| `imovelweb.callbacks.put_config` | WRITE 🔒 | `PUT /v1/configuracao/callbacks` — ⚠️ **integrator-wide** |
| `imovelweb.callbacks.subscribe` / `.unsubscribe` | WRITE 🔒 | `PUT` / `DELETE /v1/configuracao/callbacks/{evento}` |
| `imovelweb.sandbox.emit_event` | WRITE 🔒 | `POST /v1/callbacks/geracao/eventos` — **sandbox host only** |
| `imovelweb.webhook.record_delivery` | WRITE 🔒 | writes a local fixture, keyed by event id |
| `imovelweb.webhook.simulate` | WRITE 🔒 | `POST <IMOVELWEB_RECEIVER_URL>` (ours) |

🔒 = refuses without `confirm=true`, typed `412`, **no side effect**.

Three surface rules that are not negotiable:

- **`connection_status` makes zero API calls.** An agent asking "is this set up?"
  must not spend a request, and an unconfigured connector must not raise
  something an operator reads as an outage. Unconfigured is `424`, not `502`.
- **`sandbox.emit_event` hard-refuses a non-sandbox `base_url`** — a refusal, not
  a warning. It also surfaces the sandbox's 07:00–21:00 UTC-3 availability window
  as a typed error rather than a mystery timeout.
- **`callbacks.put_config` must echo the read-back diff and the previous config.**
  A `PUT` that silently drops `subscriptions` is otherwise invisible, and an
  empty subscription list delivers nothing at all, silently. The vendor cannot
  tell you what you had before, so we keep it.

Every tool result passes through `redact_secrets(text, client_secret, token,
callback_header_value)` — **three** secrets, not one. `imovelweb.leads.get_message`
and `.get_smartlead` additionally redact `identificationId` (a CPF) unless
`include_pii=true` is passed explicitly: an MCP result goes straight into a
model's context window.

## Architecture

No connector-side HTTP for the vendor API. Client, auth, contract, parser and
normalizer live in `seed/lib/backend/noctusai_lib/integrations/imovelweb/`, and
the product receiver imports the same modules — the map an agent reads and the
code that runs in production are one thing. Everything else composes `mcp/_kit`
(`bootstrap`, `settings`, `registry`, `errors`, `transport`, `seed_pin`).

`server.py` calls `_kit.bootstrap.prepare_sys_path(__file__)` **before** importing
`imovelweb.tools`. An editable install registers a meta-path finder consulted
before `sys.path`, so without it the server boots in the primary checkout and
dies with `No module named 'noctusai_lib.integrations.imovelweb'` in any
worktree — which is where it is developed.

## Config

`mcp/imovelweb/.env` (gitignored; copy `.env.example`). Two **independent**
capabilities — either works alone, and `connection_status` names whichever is
missing rather than reporting the whole connector dead:

| Capability | Vars | Source |
|---|---|---|
| vendor API (auth, callbacks, leads, agencies, sandbox) | `IMOVELWEB_CLIENT_ID`, `IMOVELWEB_CLIENT_SECRET`, `IMOVELWEB_REGION` (`br`), `IMOVELWEB_SANDBOX` (`true`/`false`) | `integracao@imovelweb.com.br` — one email for sandbox, a second for production |
| inbound (receiver simulation) | `IMOVELWEB_WEBHOOK_SECRET`, `IMOVELWEB_RECEIVER_URL` | **we choose the secret**; it must match what the product receiver validates, or a simulation proves nothing |

The webhook secret is registered *by us* as
`authorizationHeaderValue = "Basic " + base64("noctusai-imovelweb:<secret>")`.
The vendor never issues it — which is the one way this integration is easier
than Grupo OLX's.

Contract-only tools (`imovelweb.contract.*`,
`imovelweb.diagnostics.list_known_endpoints`) need **no credentials at all** and
work the moment the connector is installed.

## Registration

`.mcp.json` is **gitignored**, so the row is documented here and applied by hand:

```json
"imovelweb": {
  "command": "<repo>/venv/bin/python",
  "args": ["<repo>/mcp/imovelweb/server.py"],
  "cwd": "<repo>"
}
```

⚠️ **Register only after the branch merges into `dev`.** The `cwd` points at the
primary checkout, whose editable `noctusai_lib` has no `integrations.imovelweb`
until then — the server would `ImportError` at every session start. Until the
merge, drive it over stdio from the worktree.

Keep-list membership (`noctusai` + `supabase` + `n8n` + `waha` today) is a
context-budget decision and therefore the user's, not an agent's.

## Tests

`mcp/imovelweb/tests/test_smoke.py` must cover: every tool the registry lists;
`412` asserted **before** any side effect on each 🔒 tool; `424` when
unconfigured; and the sandbox guard refusing a production host. Run with
`cd mcp && python -m pytest imovelweb/tests -q` — check the exit code, never a
piped `tail`.
