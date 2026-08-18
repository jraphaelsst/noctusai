# `olx` MCP server — Grupo OLX portal leads (operations)

> Spec + wire detail live in `KB § CONTEXT/INTEGRATIONS/olx.md`. This is the
> operations doc: what the connector is for, its tool surface, config, and how
> to register it.

## Why it exists

`products/social-wiring` had exactly one automated lead channel (Meta Lead
Ads). Grupo OLX — **ZAP · VivaReal · OLX · ImovelWeb · Casa Mineira**, one lead
pipe for all five — is the second. Its integration is **inbound-only** and has
**no sandbox**, so this connector was built *before* the product receiver, to
make the payload contract inspectable and, more importantly, correctable
against what the API really does.

The constraint that shapes everything: OLX judges delivery purely on our HTTP
status code, retries a non-2xx 3×, and discards the lead after 14 days with no
replay API. A receiver written against unverified prose loses real leads.

## Tool surface — 9 tools

| Tool | Kind | REST / effect |
|---|---|---|
| `olx.webhook.describe_contract` | READ | none (zero IO) |
| `olx.webhook.validate_payload` | READ | none (zero IO) |
| `olx.contract.diff_observed` | READ | reads the local corpus |
| `olx.webhook.record_delivery` | WRITE 🔒 | writes a local fixture |
| `olx.webhook.simulate` | WRITE 🔒 | `POST <OLX_RECEIVER_URL>` (ours) |
| `olx.leads.push` | WRITE 🔒 | `POST /v1/addLeads` (theirs) |
| `olx.diagnostics.connection_status` | READ | none |
| `olx.diagnostics.probe` | READ | bare `GET` per baseline row |
| `olx.diagnostics.list_known_endpoints` | READ | none |

🔒 = refuses without `confirm=true`, typed `412`, **no side effect**.

## Architecture

No connector-side HTTP for the vendor API. Client, contract, parser and
normalizer live in `seed/lib/backend/noctusai_lib/integrations/olx/`, and the
product receiver imports the same modules — the map an agent reads and the code
that runs in production are one thing. Everything else composes `mcp/_kit`.

`server.py` calls `_kit.bootstrap.prepare_sys_path(__file__)` before importing
`olx.tools`. Without it the server boots in the primary checkout and dies with
`No module named 'noctusai_lib.integrations.olx'` in any worktree — which is
where it is developed.

## Config

`mcp/olx/.env` (gitignored; copy `.env.example`). Two **independent**
capabilities — either works alone, and `connection_status` names whichever is
missing rather than reporting the whole connector dead:

| Capability | Vars | Source |
|---|---|---|
| inbound (receiver simulation) | `OLX_WEBHOOK_SECRET`, `OLX_RECEIVER_URL` | the per-CRM key issued at homologation |
| outbound (Gestor de Leads) | `OLX_API_KEY`, `OLX_AGENT_NAME` | Gestor de Leads setup — `integracaoleads@grupozap.com` |

The webhook secret is **one per CRM, not per advertiser**, and must match what
the product receiver validates or a simulation proves nothing.

## Gated-capability honesty

Unconfigured ⇒ typed `424` with the exact env vars to set, never a fabricated
success. Unreachable / non-JSON ⇒ `502`. The vendor's own 4xx passes through.
The API key is redacted out of any upstream text before it reaches an error
message — vendors echo credentials in error bodies, and a tool result goes
straight into a model's context.

## The observed corpus is PII

`mcp/olx/fixtures/observed/*.json` holds real consumer names, emails and phone
numbers — LGPD personal data. Gitignored, and it must stay that way: git
history cannot honour a deletion request. Local diagnostic aid, not an artifact.

## Registration

`.mcp.json` is **gitignored** (per-machine, absolute `cwd`), so the row lives
here, not in a commit. It is **registered and live as of 2026-08-17**, in the
pre-merge form:

```json
"olx": {
  "command": "mcp/noctusai/.venv/bin/python",
  "args": ["/Users/rapha/.../.claude/worktrees/olx-portal-leads-mcp/mcp/olx/server.py"],
  "cwd": "/Users/rapha/Documents/repository/NoctusAI/noctusai"
}
```

🔴 **Repoint this at the merge.** The absolute `args` path is the worktree,
because `cwd`'s editable `noctusai_lib` gains `integrations.olx` only when
`feat/olx-portal-leads-mcp` lands — the primary-path form would ImportError at
every session start until then. Once merged, and **before**
`task_branch action=cleanup` removes the worktree, replace `args` with the
durable relative form:

```json
  "args": ["mcp/olx/server.py"],
```

Cleaning the worktree without repointing leaves a server row whose file is
gone: loud at session start, one line to fix, but it will look like a broken
connector to whoever hits it first.

Keep-list membership is the user's call (`CLAUDE.md` §1); this row was added on
their explicit instruction so the API can be validated against the live key
next session.

## Tests

```
cd mcp && python -m pytest olx/tests -q      # 33 tests, no network
```

Outbound client swapped via the DI seam (`olx.client.configure_client`); the
simulator exercised against a patched `urlopen` at the **external** boundary.
Our own code always runs for real.

## First real use

Not yet — Gate 1 in `projects/olx-portal-leads-ingestion/PROJECT.md` is the
first live pass and needs the real key. Until then
`describe_contract` reports `verified_against_live_traffic: false` and every
`probe` row is `unverified`, both deliberately.
