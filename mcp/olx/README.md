# `mcp/olx` — Grupo OLX portal-lead connector

Covers **ZAP · VivaReal · OLX · ImovelWeb · Casa Mineira**. One connector,
because the portals share one lead pipe — a per-portal connector would be
five copies of this directory.

## Why it exists

The lead integration is **inbound**: OLX POSTs one lead per request at a URL
we register, authenticated with HTTP Basic (`vivareal:<SECRET_KEY>`, one key
per CRM). There is no pull API and **no sandbox**. Delivery is judged purely
on our HTTP status code — the response body is ignored — and a non-2xx is
retried 3× then discarded after 14 days with no replay.

That combination is why this connector was built *before* the product
receiver: writing a receiver against the vendor's prose and discovering the
divergence in production means discovering it on leads that cannot be
recovered. So the connector's job is to make the contract inspectable,
testable, exercisable and — the part that matters — **correctable against
what the API really does**.

## Tool surface

| Tool | Kind | What it does |
|---|---|---|
| `olx.webhook.describe_contract` | READ, zero IO | The full documented contract: auth, delivery model, every field, enums, response semantics, retry policy, JSON Schema, sample. No credentials needed. |
| `olx.webhook.validate_payload` | READ, zero IO | Checks one body against the contract. Returns `would_return_4xx` — the ONE case where a non-2xx is correct. |
| `olx.webhook.record_delivery` | WRITE 🔒 | Persists a REAL body into the observed corpus. Unparseable bodies are recorded too — they are the shapes the receiver would drop. |
| `olx.contract.diff_observed` | READ | Diffs the corpus against the contract: undocumented fields, never-seen fields, required-but-null fields, novel enum values. **The doc-vs-reality loop.** |
| `olx.webhook.simulate` | WRITE 🔒 | POSTs a synthetic lead at OUR receiver with a real Basic header — the stand-in for the missing sandbox. Rehearses reject paths too (`wrong_secret`, null `client_listing_id`). |
| `olx.leads.push` | WRITE 🔒 | `POST /v1/addLeads` — pushes a lead INTO the client's OLX inbox. The only authenticated endpoint OLX exposes, so also the only live proof a key works. |
| `olx.diagnostics.connection_status` | READ, no API call | Which halves are configured, and whether the contract has been verified yet. |
| `olx.diagnostics.probe` | READ | What each endpoint actually answers. Read `unexpected` and `unverified`, not `results`. |
| `olx.diagnostics.list_known_endpoints` | READ, no API call | Endpoint catalog + vendor doc URLs + the support addresses to email for a key or an ImovelWeb activation code. |

Every write refuses without `confirm=true` and returns a typed `412` **before
any side effect**.

## Architecture

No connector-side HTTP for the vendor API. The client, the payload contract,
the parser and the normalizer all live in
`seed/lib/backend/noctusai_lib/integrations/olx/`, and the **product receiver
imports the same modules**. The map an agent reads and the code that runs in
production are one thing; two copies would disagree within a release and the
disagreement would look like leads vanishing.

(`olx.webhook.simulate` does open a socket — at *our* receiver, not at OLX.)

Everything else is the shared kit: `_kit.settings`, `_kit.registry`,
`_kit.errors`, `_kit.bootstrap`. See `mcp/_kit/README.md`.

## Config

`mcp/olx/.env` (gitignored — copy `.env.example`). Two independent
capabilities; either half works alone, and `connection_status` names whichever
is missing:

- **inbound** — `OLX_WEBHOOK_SECRET`, `OLX_RECEIVER_URL`
- **outbound** — `OLX_API_KEY`, `OLX_AGENT_NAME`

The webhook secret must match what the product receiver validates, or a
simulation proves nothing.

## The observed corpus is PII

`fixtures/observed/*.json` holds **real consumer names, emails and phone
numbers** — LGPD personal data. It is gitignored and must stay that way: git
history cannot honour a deletion request. Treat it as a local diagnostic aid,
not an artifact.

## Registration

Registered in `.mcp.json`. Adding it to the session keep-list is the user's
call (`CLAUDE.md` §1 context-budget rule).

## Tests

```
cd mcp && python -m pytest olx/tests -q
```

33 tests, no network. The outbound client is swapped through the DI seam
(`olx.client.configure_client`); the simulator is exercised against a patched
`urlopen` at the **external** boundary — our own code always runs for real.

## Status

⚠️ **The contract is transcribed from the vendor's documentation and has never
been checked against live traffic.** `describe_contract` reports
`verified_against_live_traffic: false` and every endpoint baseline row is
`unverified` on purpose — a guessed expected-status would make the probe report
lie, and an operator who learns the report lies stops reading it.

Gate 1 in `projects/olx-portal-leads-ingestion/PROJECT.md` is the pass that
fixes that, and it needs the real key.
