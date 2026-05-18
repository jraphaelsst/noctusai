# `mcp/meta` — Meta-family connector MCP server

Composes `mcp/_kit` (the shared connector-MCP boilerplate) exactly the
way `mcp/vista` does — bare `sys.path` insert → `_kit.bootstrap`
composition, frozen `MetaConnectorSettings(ConnectorSettings)`,
`_kit.registry.build_registry` aggregation, `_kit.errors.typed_error`
envelope. Nothing generic is re-implemented here.

## Tool surface

### Shipped (Wave 2)

| Tool | Side-effect | Backed by (seed) |
|---|---|---|
| `meta.whatsapp.send_text` | **OUTBOUND — confirm-gated** | `noctusai_lib.integrations.whatsapp.get_whatsapp_client` + `chat_id_for_phone` |
| `meta.whatsapp.parse_inbound` | none (pure) | `noctusai_lib.integrations.whatsapp.parse_waha_inbound_message` |

`meta.whatsapp.send_text` requires `confirm: true`. Without it the tool
returns a typed error (`error_class=ConfirmationRequiredError`,
`status=412`) and performs **no** side-effect — the confirm-then-execute
contract (`KB § PATTERNS/llm-bot-security.md`). A structured
`logger.info` audit line is emitted on both the blocked path and the
confirmed path (before the provider call, so an attempted send is
recorded even if the provider then raises).

Deferred-config: with no `WAHA_BASE_URL` the seed factory returns
`FakeWahaClient`, so the server boots with zero creds and both tools
still answer deterministically. With creds it returns the real
httpx-backed `WahaClient`.

### NOT shipped — verify-the-seed-ships-it gap (Wave 3 blocker)

`meta.facebook.*`, `meta.instagram.*`, and `meta.diagnostics.*` from the
Wave-2 brief are **not** built. They were specified to wrap
`noctusai_lib.integrations.meta` (`get_meta_adapter`, `FacebookPage`,
`InstagramAccount`, `MetaGraphError`, `discover_app_permissions`,
`resolve_oauth_scopes`, `MetaConnectionStatus`). **That package does not
exist in the tree** — `seed/lib/backend/noctusai_lib/integrations/`
ships no `meta/`, and none of those symbols are defined anywhere in
`seed/`. (The only "meta" code is the WhatsApp Cloud-API client at
`integrations/whatsapp/meta_cloud_client.py`, which is unrelated to the
Graph API.)

Building those tools would mean re-implementing the Graph-API adapter
connector-side — a structural fork the brief explicitly forbids
("NOT re-implementing anything — thin wrappers over the lib") and a
`verify-the-seed-ships-it` violation. Per that rule (Gap + N=1 consumer
→ ship against what the seed ships, surface the follow-up), the
WhatsApp slice ships now and the Graph-API surface is surfaced as a
Wave-3 blocker requiring a seed `noctusai_lib.integrations.meta` project
first.

`settings.py` already declares `META_SYSTEM_USER_TOKEN` / `META_APP_ID`
/ `META_APP_SECRET` so the env contract is stable for when that surface
lands — the leaf modules drop into `tools/__init__.py::LEAF_MODULES`
unchanged at that point.

## Settings (`mcp/meta/.env` or env — env wins)

| Env var | Field | Used by |
|---|---|---|
| `WAHA_BASE_URL` | `waha_base_url` | shipped — real-vs-Fake signal for the WhatsApp slice |
| `WAHA_API_KEY` | `waha_api_key` | shipped |
| `WAHA_EXTERNAL_BASE_URL` | `waha_external_base_url` | carried (tunnel/webhook URL emission) |
| `META_SYSTEM_USER_TOKEN` | `meta_system_user_token` | dormant — Graph-API surface (Wave 3) |
| `META_APP_ID` | `meta_app_id` | dormant — Graph-API surface (Wave 3) |
| `META_APP_SECRET` | `meta_app_secret` | dormant — Graph-API surface (Wave 3) |

## Run

```
python mcp/meta/server.py            # stdio entry point (server name "meta")
cd mcp && python -m pytest meta/tests/ -q
```

Registration in `.mcp.json` is a separate user decision (not done here).
