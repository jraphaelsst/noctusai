# `mcp/meta` — Meta-family connector MCP server

Composes `mcp/_kit` (the shared connector-MCP boilerplate) exactly the
way `mcp/vista` does — bare `sys.path` insert → `_kit.bootstrap`
composition, frozen `MetaConnectorSettings(ConnectorSettings)`,
`_kit.registry.build_registry` aggregation, `_kit.errors.typed_error`
envelope. Nothing generic is re-implemented here.

## Tool surface

### WhatsApp slice

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

### Graph read-only surface (Facebook + Instagram + diagnostics)

Wraps `noctusai_lib.integrations.meta` — present in the tree post
social-wiring absorption (canonical seed Protocol + Fake + Real(OAuth,
dual-auth) + factory; sibling to `google_calendar/`, `vista/`).

| Tool | Side-effect | Backed by (seed) |
|---|---|---|
| `meta.facebook.list_pages` | none (pure) | `get_meta_adapter(...).list_facebook_pages()` |
| `meta.facebook.list_page_posts` | none (pure) | `.list_facebook_posts(page_id, limit)` |
| `meta.facebook.post_insights` | none (pure) | `.get_facebook_post_insights(post_id, page_id)` |
| `meta.instagram.list_accounts` | none (pure) | `.list_instagram_accounts()` |
| `meta.instagram.list_media` | none (pure) | `.list_instagram_media(ig_user_id, limit)` |
| `meta.instagram.media_insights` | none (pure) | `.get_instagram_media_insights(media_id)` |
| `meta.diagnostics.connection_status` | none (pure) | `.status()` → `MetaConnectionStatus` |
| `meta.diagnostics.discover_scopes` | none (pure) | `resolve_oauth_scopes(...)` |

**READ-ONLY v1.** The seed `MetaAdapter` Protocol exposes no write
methods — posting (FB Page post, IG publish) and ads are out of scope
(Meta App Review gates the write scopes); no such tools are exposed.
Each tool surfaces `auth_mode` (`system_user` / `user_oauth` / `none`)
so the silent-empty-data failure mode on Business-Portfolio-owned
assets is visible. `MetaGraphError` carries `.http_status` (not
`.status`); the leaf `_meta_error` enrichment exposes `http_status` /
`is_auth_error` / `is_rate_limited` on the typed-error envelope so the
host LLM can branch deterministically (re-consent vs back-off vs hard
failure) even though `_kit.errors.typed_error` only probes `.status`.

Deferred-config: with no `META_SYSTEM_USER_TOKEN` (and no OAuth
resolver) `get_meta_adapter` returns `FakeMetaAdapter`, so the server
boots with zero creds and every Graph tool answers deterministically
(empty unless seeded, `auth_mode="none"`). `access_token` on a
`FacebookPage` is **never** mapped onto the wire shape.

## Settings (`mcp/meta/.env` or env — env wins)

| Env var | Field | Used by |
|---|---|---|
| `WAHA_BASE_URL` | `waha_base_url` | shipped — real-vs-Fake signal for the WhatsApp slice |
| `WAHA_API_KEY` | `waha_api_key` | shipped |
| `WAHA_EXTERNAL_BASE_URL` | `waha_external_base_url` | carried (tunnel/webhook URL emission) |
| `META_SYSTEM_USER_TOKEN` | `meta_system_user_token` | shipped — Graph adapter auth (System User Token → live `MetaOAuthAdapter`; absent → `FakeMetaAdapter`) |
| `META_APP_ID` | `meta_app_id` | shipped — `meta.diagnostics.discover_scopes` app-permissions discovery |
| `META_APP_SECRET` | `meta_app_secret` | shipped — `meta.diagnostics.discover_scopes` app-permissions discovery |

## Run

```
python mcp/meta/server.py            # stdio entry point (server name "meta")
cd mcp && python -m pytest meta/tests/ -q
```

Registration in `.mcp.json` is a separate user decision (not done here).
