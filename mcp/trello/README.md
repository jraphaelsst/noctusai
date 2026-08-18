# `mcp/trello` — Trello / Atlassian connector MCP

## Why it exists

**Primary job: a queryable map of Trello's product surface.** The user is
building a Trello-grade card in `products/social-wiring`
(`project-history/roadmaps/lead-card-hub-2026-08.md`), and needs a truthful,
machine-readable answer to "what does Trello actually expose on a card?"
instead of a guess from memory or screenshots. This connector is **not**
being used to drive a live Trello account today — the `trello.contract.*`
tools are the point, and they work with **zero network calls and zero
credentials, forever**, because the contract is a vendored copy of Trello's
own OpenAPI 3 spec (`contract/swagger.v3.json` — see
`contract/PROVENANCE.md` for source, fetch date, sha256).

**Secondary job:** a correct, confirm-gated live client against the real
Trello REST API, for whenever a product does start talking to Trello.

## Tool surface (18 tools)

| Tool | Kind | What it does |
|---|---|---|
| `trello.contract.list_endpoints` | READ, zero IO | All 261 operations; filter by `resource`/`method`/`q`. |
| `trello.contract.describe_operation` | READ, zero IO | Full detail on one operation — params, request body, response schema ref. |
| `trello.contract.describe_model` | READ, zero IO | A named schema (`Card`, `Checklist`, `Label`, …), properties flattened one level. |
| `trello.contract.card_surface` | READ, zero IO | **Call this first.** The 42 `/cards/*` operations grouped by affordance, plus the `Card` schema (badges flattened) and the exact `PUT /cards/{id}` writable-field list. |
| `trello.contract.capability_map` | READ, zero IO | The design bridge: each Trello affordance → its status (`exists`/`build-new`/`no-equivalent`) in our lead-card-hub domain, sourced from the roadmap. |
| `trello.diagnostics.connection_status` | READ, zero API calls | Is `TRELLO_API_KEY`/`TRELLO_TOKEN` configured? |
| `trello.diagnostics.probe` | READ, one live call | `GET /members/me` — proves the key+token pair actually works. |
| `trello.boards.list` | READ, one live call | Boards a member belongs to. |
| `trello.lists.list` | READ, one live call | Lists on a board. |
| `trello.cards.list` | READ, one live call | Cards on a board OR a list. |
| `trello.cards.get` | READ, one live call | One card, with an `include` option for attachments/checklists/members/actions. |
| `trello.checklists.get` | READ, one live call | One checklist (with its check items). |
| `trello.labels.list` | READ, one live call | Labels defined on a board. |
| `trello.actions.list` | READ, one live call | A card's comment/activity thread. |
| `trello.cards.create` | WRITE 🔒 | Create a card. Confirm-gated (412). |
| `trello.cards.update` | WRITE 🔒 | Update a card. `fields` keys are validated against the vendored `PUT /cards/{id}` param list — an unknown key is a 422 before the confirm check even runs. Confirm-gated (412). |
| `trello.cards.comment_add` | WRITE 🔒 | Post a comment on a card. Confirm-gated (412). |
| `trello.checklists.create` | WRITE 🔒 | Create a checklist on a card. Confirm-gated (412). |

Every write refuses without `confirm=true` and returns a typed `412`
**before any side effect**. Every tool description says up front whether it
costs a network call.

## Where Trello's own spec will mislead you

These are properties of the **vendor's** document, not bugs in this connector.
Each one has already cost someone time, so they are written down rather than
re-discovered.

- **`describe_model('Checklist')` looks broken. It is not.** Trello's spec
  documents that schema as essentially `{id}` — no `name`, no `pos`, no items.
  The real shape only appears in the nested response bodies (`GET
  /checklists/{id}`, and the `checklists` array inside a card fetched with the
  right `include`). **Do not design a checklist model off the named schema**,
  and do not go debugging the `describe_model` handler when it returns almost
  nothing — ask `describe_operation` for the operation instead.
- **`Action` has no flat comment text.** The comments/activity model carries
  `data`, `date`, `display`, `memberCreator`, `type` — and the actual comment
  body lives *inside* the free-form `data` blob, whose shape varies by `type`.
  Any unified timeline built against this needs a **per-`type` parser**, not one
  flat comment model. (This is the finding that confirmed the discriminated-union
  timeline in the card-hub contract was the right shape.)
- **`Card.badges` is richer than the obvious counts** — beyond `checkItems` /
  `checkItemsChecked` / `comments` / `attachments` / `description` / `due` /
  `dueComplete` it also carries `attachmentsByType`, `viewingMemberVoted`,
  `location` and `fogbugz`.
- **`Member` carries more than an id and a name** — `bio`, `avatarUrl`,
  `initials`, `status` are all there, which matters if you are modelling an
  assignee UI rather than just a foreign key.

## Architecture

**No `noctusai_lib.integrations.trello` seed adapter, deliberately.** No
product consumes Trello today, and a seed IO module (Protocol+Fake+Real+
factory, `KB § PATTERNS/backend/seed-fake-real-adapter.md`) would have to
ship Fake+Real+factory for a consumer that does not exist. Instead this
connector is **self-contained** — the same shape `mcp/waha` and
`mcp/hostinger` use — with the HTTP mechanics living in `client.py`/`api.py`,
composing `_kit.transport.request_json` directly. If that call is wrong,
surface it; don't build the seed adapter anyway.

- `spec.py` — reads the vendored `contract/swagger.v3.json`. The substrate
  for every `trello.contract.*` tool.
- `settings.py` — `TrelloConnectorSettings` (`api_key` + `token`).
- `api.py` — `TrelloApiError`, the 424 not-configured gate, and
  `request_json` (composes `_kit.transport.request_json`, injecting
  `key`/`token` as **query params** — Trello's `components.securitySchemes`
  declares both as `type: apiKey, in: query`, unlike every other connector
  in this repo, which authenticates via a header).
- `client.py` — `TrelloClient`, a thin domain-shaped wrapper (`get_card`,
  `update_card`, …) around `api.request_json`, plus the `get_client()`/
  `configure_client()` DI seam every tool builds through (mirrors
  `mcp/n8n/client.py`'s shape, minus the seed adapter it wraps).
- `tools/contract.py` — the zero-IO tools; owns `CARD_AFFORDANCE_GROUPS`'
  classification and the `CAPABILITY_MAP` module-level data structure.
- Everything else is the shared kit: `_kit.settings`, `_kit.registry`,
  `_kit.errors`, `_kit.bootstrap`, `_kit.transport`. See `mcp/_kit/README.md`.

## Config

`mcp/trello/.env` (gitignored — copy `.env.example`):

```
TRELLO_API_KEY=...   # https://trello.com/app-key
TRELLO_TOKEN=...     # the "Token" link on that same page
```

Neither is required for the `trello.contract.*` tools.

## Registration

Registered in `.mcp.json` as `"trello"`, pointing at the **repo-root**
`mcp/trello/server.py` path — not a worktree path. (The existing `"olx"`
entry in `.mcp.json` points into a worktree; that is drift, not a pattern
to copy — flagged separately for the tech-lead to fix.)

## Tests

```
cd mcp && python -m pytest trello/tests -q
```

67 tests, no network. `trello.contract.*` tests run with genuinely zero
credentials and zero patched transport — that IS the guarantee under test.
Live-tool tests patch either `trello.api.request_json` (wiring/shaping) or
`_kit.transport.urlopen` (actual wire shape — proves `key`/`token` really do
go out as query params). Our own code (`TrelloClient`, `api.require_configured`)
is never patched.

`tests/test_contract_spec_facts.py` pins the verified facts (261 total
operations, the 18-resource breakdown, the `Card.badges` field set, the
17-name `PUT /cards/{id}` writable list) directly against the vendored spec
file — a future spec refresh that changes any of them fails loudly instead
of the tools silently answering something new.

## Refreshing the vendored spec

See `contract/PROVENANCE.md` § Refreshing this file.
