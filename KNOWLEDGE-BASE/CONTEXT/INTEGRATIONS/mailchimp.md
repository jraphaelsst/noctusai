# Mailchimp — Marketing API v3 (consume-side reference)

> Seed adapter: `noctusai_lib.integrations.mailchimp` · first consumer: `products/social-wiring/backend/app/modules/mailchimp/` (shipped 2026-06-10). Mailchimp is the SOURCE OF TRUTH — the product proxies live; no local mirror.

## What ships (seed)

- **Module**: `seed/lib/backend/noctusai_lib/integrations/mailchimp/` — Protocol + Fake + Real + factory (`seed-fake-real-adapter` shape).
- **Factory**: `get_mailchimp_client(api_key=None, *, server_prefix=None) -> MailchimpClient` — Fake when no key; `server_prefix` defaults to `parse_server_prefix(api_key)` (key suffix `xxxx-us6`; malformed suffix raises `ValueError`).
- **Real**: `HttpxMailchimpClient` — plain httpx (the official `mailchimp-marketing` SDK is unmaintained since 2022 — do NOT depend on it). Basic auth `("anystring", api_key)`, base `https://{dc}.api.mailchimp.com/3.0`, ctor `transport=` seam for `httpx.MockTransport` (tests exercise the real `_request`, no monkey-patching).
- **Errors** (single hierarchy — consumers MUST import these, never redefine; a local redefinition makes `except` silently miss the real adapter's raises): `MailchimpError` → `MailchimpAuthError` (MC 401/403) / `MailchimpNotFoundError` (404) / `MailchimpRateLimitedError` (429) / `MailchimpRejectedError` (400/422, carries MC problem+json title/detail) / `MailchimpUnreachableError` (network/timeout/5xx).
- **Surface** (30 async methods): `ping` · audiences (`list_audiences`/`get_audience`) · members (`list/get/upsert_member`, `set_member_tags`, `archive_member`) · static segments (`list/create_static_segment/update/delete_segment`, `list/add/remove_segment_member`) · templates (`list/get/create/update/delete_template`, `get_template_default_content`) · campaigns (`list/get/create/update/delete_campaign`, `set_campaign_content`, `send/schedule/unschedule_campaign`, `send_test`).
- **Mappers**: `subscriber_hash(email)` = md5(lower(strip(email))) — the member id in all `/members/{hash}` paths (PUT = upsert with `status_if_new`); `template_edit_url(dc, id)` = `https://{dc}.admin.mailchimp.com/templates/edit?id={id}` (best-effort for drag-and-drop templates).

## Consume recipe (cited consumer: social-wiring)

1. **Credentials per-org**: Fernet-TEXT row (`mailchimp_connections`: org_id UNIQUE, encrypted_api_key TEXT, server_prefix, audience_id) via `credential_vault.require_fernet` — TEXT not bytea (PostgREST `\x`-hex trap). Migration mirror: `products/social-wiring/backend/migrations/013_mailchimp_connections.sql`.
2. **DI seams** (`app/modules/mailchimp/deps.py`): `get_mailchimp_client_factory()` lazy-imports the seed factory; `require_mailchimp_client` resolves the org row (decrypt) → `(client, record)` or 503 `mailchimp_not_configured`. Tests override the factory with `FakeMailchimpClient` — zero patching.
3. **Error translation once**: `translate_mailchimp_errors()` asynccontextmanager maps the hierarchy → `AppException` (NOT `HTTPException` — the seed handler stringifies dict details). Wire envelope: `{"error":{code,message}}`; codes `mailchimp_not_configured` 503 · `mailchimp_auth_failed` 502 · `not_found` 404 · `mailchimp_rate_limited` 503 · `mailchimp_rejected` 400 · `mailchimp_unreachable` 502. The seed FE `extractErrorMessage` parses `error.message` as its FIRST branch.
4. **Key validation on save**: PUT connection → `parse_server_prefix` (400 on malformed) → live `ping()` → encrypt+upsert; api_key is write-only, never returned. `GET /connection` is the FE gate probe — ALWAYS 200 with `connected: bool`.

## Vendor gotchas

- **Audience caps by plan**: Free=1, Essentials=3, Standard=5 — model "multiple contact lists" as **static segments** inside one audience (campaigns target `recipients.segment_opts.saved_segment_id`), never as audiences.
- **`schedule_campaign`**: ISO8601 UTC, quarter-hour boundaries (`:00/:15/:30/:45`) only.
- **Member DELETE = archive**; permanent delete is a separate action endpoint. Deleting an AUDIENCE loses all history — never expose it casually.
- **Webhooks**: Standard+ plan only; payloads are form-encoded (`application/x-www-form-urlencoded`), not JSON. Not consumed yet (follow-up).
- **Rate limits**: 10 concurrent connections, 120s timeout; pagination `count` (max 1000) + `offset`, responses carry `total_items`.

## Gaps / not-yet-consumed

Campaign raw-HTML content editing (adapter ships `set_campaign_content(html=)`, UI only wires `template_id`); list webhooks; batch operations (`/batches`); merge-fields management beyond FNAME/LNAME.
