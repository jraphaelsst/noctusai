# `imovelweb` connector MCP

ImovelWeb · Wimoveis · Casa Mineira portal leads, via **OpenNavent**
(Navent / Grupo QuintoAndar). **Not Grupo OLX** — that is a different vendor
with its own connector at `mcp/olx`, even though its Gestor de Leads also
ships an ImovelWeb bridge that stamps leads `leadOrigin: "Grupo OLX"` and
loses the portal name. Wiring both pipes for one advertiser delivers the
same enquiry twice under two different ids.

- Operations doc + registration row → `KB § MCP-SERVERS/imovelweb.md`
- Wire contract → `KB § CONTEXT/INTEGRATIONS/imovelweb.md`
- Project → `projects/imovelweb-portal-leads-ingestion/PROJECT.md`

## Run

```bash
python mcp/imovelweb/server.py          # stdio
cd mcp && python -m pytest imovelweb/tests -q
```

Check the **exit code**, never a piped `tail` — `cmd | tail` returns tail's
status, which is always 0.

## What it is for

Three facts drive every design decision in here:

1. **1.5 seconds** to answer a delivery, or the vendor scores it an error.
2. **72 hours** of retries, then the callback goes `VENCIDO`. There is a
   pull API, so a miss is recoverable — reconciliation, not the webhook, is
   the durability guarantee.
3. **No signature.** Only the static header we ourselves registered.

And two capabilities this connector has that the OLX one could not:

- **A public, unauthenticated OpenAPI spec** on both hosts, so
  `imovelweb.diagnostics.fetch_swagger` closes the doc-vs-reality loop for
  the API surface without credentials.
- **A sandbox event simulator**, so `imovelweb.sandbox.emit_event` proves
  the end-to-end contract before a single real lead exists. That is why the
  project's product slice comes after Gate 1 rather than after production
  traffic.

## Surface (19 tools)

| Tool | Kind |
|---|---|
| `imovelweb.contract.describe` · `.validate_payload` · `.diff_observed` | READ — zero IO, **no credentials** |
| `imovelweb.diagnostics.list_known_endpoints` | READ — zero IO |
| `imovelweb.diagnostics.connection_status` | READ — **zero API calls** |
| `imovelweb.diagnostics.probe` | READ |
| `imovelweb.diagnostics.fetch_swagger` | READ — public spec, no credentials |
| `imovelweb.callbacks.get_config` | READ |
| `imovelweb.agencies.list` | READ |
| `imovelweb.leads.get_message` · `.list_messages` · `.get_smartlead` · `.list_contact_actions` | READ |
| `imovelweb.callbacks.put_config` | WRITE 🔒 — ⚠️ **integrator-wide** |
| `imovelweb.callbacks.subscribe` · `.unsubscribe` | WRITE 🔒 |
| `imovelweb.sandbox.emit_event` | WRITE 🔒 — **sandbox host only** |
| `imovelweb.webhook.record_delivery` · `.simulate` | WRITE 🔒 |

🔒 refuses without `confirm=true`, typed **412**, **no side effect** — the
gate is evaluated before settings are even read.

## Four things that are deliberate

**`connection_status` makes zero API calls.** An agent asking "am I set up?"
must not spend a request, and an unconfigured connector must not raise
something an operator reads as an outage. Unconfigured is **424**, never
502, and never a fabricated success.

**`put_config` is the dangerous one.** `PUT /v1/configuracao/callbacks`
takes no agency code, so it redirects *every* agency's leads at once. It
refuses a localhost / private / ephemeral-tunnel URL, reads the previous
config first (the vendor cannot tell you afterwards what you had), and
diffs what was applied against what was asked. The failure it exists to
catch is silent: a config with a correct URL and an empty `subscriptions`
list delivers nothing while reporting perfect health.

**`probe` cannot prove a path exists.** `/v1/**` answers 401 *before*
routing, so a bogus path returns the same 401 as a real one. Every such row
is marked non-discriminating; `fetch_swagger` is what actually answers path
existence.

**Secrets and CPFs never leave here.** Every result passes through
`redact_secrets` with all three secrets (`client_secret`, the bearer token,
the callback header value). `identificationId` is a CPF and is replaced
with a placeholder unless `include_pii=true` — the key is kept so the fact
that one arrived stays visible. An MCP result goes straight into a model's
context window, which is a log we do not control.

## Architecture

No connector-side HTTP for the vendor API. Client, auth, contract, parser
and normalizer live in `noctusai_lib.integrations.imovelweb`, and the
product receiver imports the same modules — the map an agent reads and the
code that runs in production are one thing. Everything else composes
`mcp/_kit`.

`server.py` calls `prepare_sys_path(__file__)` **before** importing
`imovelweb.tools`: an editable install registers a meta-path finder
consulted ahead of `sys.path`, so without it the server boots in the
primary checkout and dies with `No module named
'noctusai_lib.integrations.imovelweb'` in any worktree — which is where it
gets developed.

`httpx` is imported lazily, inside the client factory, so a broken or
missing transport cannot take down the zero-IO tools. Those are what
somebody reaches for *during* an incident; a connector that dies at import
is one more thing that is down.

## Config

`mcp/imovelweb/.env` (gitignored) — copy `.env.example`. Every connector
owns its auth store rather than inheriting the repo `.env`.
