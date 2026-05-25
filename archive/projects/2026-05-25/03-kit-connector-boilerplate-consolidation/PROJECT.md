# `_kit` connector-boilerplate consolidation — Project Document

> **Follow-up filed per the DRY recurrence rule (N=4 → MUST formalize).** Not started. Surfaced by the Hostinger-MCP build (2026-05-21).

- **Created:** 2026-05-21
- **Status:** ✅ DONE (2026-05-25) — Wave 1 (`_kit.transport.request_json` + `BROWSER_USER_AGENT` + `confirmation_required_message`, 12 tests) SHIPPED `e1b2a363`; Wave 2 (n8n pilot `7c6f426c` + waha · hostinger · supabase extend-wave) refactored onto the seam; cloudflare = documented carve-out (richer `cf_code`-from-error-body contract — accept-with-rationale). **4/5 connectors consume `_kit.transport`** (vista delegates to the seed `VistaClient` — N/A; cloudflare keeps bespoke transport, N=1 exception). All 6 suites green (`_kit` 12 + n8n/waha/hostinger/cloudflare/supabase = 141). Wave 3 docs done.
- **Owner:** Raphael · Claude
- **Project slug:** `kit-connector-boilerplate-consolidation` @ `projects/` (platform-infra)

## 1. Context

Connector MCPs (`mcp/vista`, `mcp/n8n`, `mcp/waha`, `mcp/hostinger`, and now `mcp/cloudflare` in flight) each **hand-roll near-identical boilerplate beyond `mcp/_kit`**: the `urllib` `request_json` seam, the `ConfirmationRequiredError`/412 confirm-gate, the env-carrier `settings.py` shape. The Hostinger build flagged this at **N=4** (MUST-formalize per `KB § PATTERNS/project-execution.md §2.7`). A genuinely new wrinkle also appeared worth lifting: a **browser-style `User-Agent`** in `request_json` (Cloudflare's WAF 403s the default urllib UA — hit live on the Hostinger API; pre-empted in the Cloudflare connector).

## 3a. Seed-first analysis

The recurring shape is cross-connector infrastructure ⇒ belongs in **`mcp/_kit`** (the shared connector layer), not re-authored per connector. Per-connector code should shrink to: endpoint map + Pydantic types + tool registration. Target per-connector boilerplate LoC ≈ 0 for the request seam / confirm-gate / settings carrier.

## 4. Scope

**In scope:** extract into `mcp/_kit` — (1) a shared `request_json` HTTP helper (Bearer/header auth injection, browser UA, CF-envelope-aware error typing hook), (2) the `ConfirmationRequiredError`/confirm-gate decorator or helper, (3) a settings-carrier base. Then refactor the 4 existing connectors onto it (pilot: hostinger + n8n first), keeping behavior identical (tests stay green).

**Out of scope:** changing any connector's tool surface or auth store.

## 6. Phases (suggestive)
1. Design the `_kit` shared request/confirm/settings API (back-compat; connectors opt in).
2. Implement in `_kit` + tests.
3. Refactor pilots (hostinger, n8n) → green.
4. Refactor remaining (waha, vista, cloudflare) → green.
5. Three-way sync (KB `_kit` README + `mcp-tool-conventions.md` + memory).

## 9. Success criteria
- One shared request seam + confirm-gate + settings base in `_kit`; the connectors consume it; all connector test suites green; no tool-surface change.
- **Met (2026-05-25):** `_kit.transport.request_json` + `confirmation_required_message` shipped. **4 of 5** envelope-free connectors (n8n · waha · hostinger · supabase) delegate transport to the seam. **Cloudflare is the documented N=1 exception** (its `cf_code`-from-HTTP-error-body contract exceeds the seam's `(message, status)` error interface — accept-with-rationale, revisit at N=2). vista is N/A (delegates to the seed `VistaClient`). All 6 suites green (141 tests); zero tool-surface change.

## 11. Change log
| Date | Change | By |
|---|---|---|
| 2026-05-21 | Filed from `production-deploy-migration` after Hostinger MCP flagged N=4 connector-boilerplate recurrence (+ the browser-UA-vs-CF-WAF wrinkle worth lifting) | Claude |
| 2026-05-25 | Wave 1 shipped: `_kit.transport.request_json` (auth_header/user_agent/error_cls/empty_result params) + `BROWSER_USER_AGENT` + `errors.confirmation_required_message` + 12 unit tests (`e1b2a363`). Module named `transport` not `http` (avoids stdlib-`http` shadow on sys.path). | Claude |
| 2026-05-25 | Wave 2 PILOT — n8n/api.py refactored onto `_kit.transport` (kept N8nApiError + /api/v1 normalizer + 424 gate; tests patch the `request_json` wrapper ⇒ zero test churn). Suite green (32). **Recipe (proven), per remaining connector:** (1) `from _kit.transport import request_json as _http_request_json` + `from _kit.errors import confirmation_required_message`; (2) keep `<Vendor>ApiError` + the config/424 gate + any envelope handling (cloudflare); (3) request_json body → build url via the connector's normalizer, then `return _http_request_json(method, url, auth_header=(<hdr>,<val>), user_agent=BROWSER_USER_AGENT if WAF else default, params=..., body=..., timeout=..., error_cls=<Vendor>ApiError, empty_result={}/None, label=...)`; (4) ConfirmationRequiredError → `confirmation_required_message(action[, effect][, noun=...])`. ⚠ cloudflare/supabase tests patch `<conn>.api.urllib.request.urlopen` — those need re-pointing to `_kit.transport.urlopen` (n8n/waha/hostinger patch the `request_json` wrapper ⇒ no change). | Claude |
| 2026-05-25 | Wave 2 EXTEND-WAVE — waha · hostinger · supabase refactored onto `_kit.transport` (each keeps its `<Vendor>ApiError` + 424 gate + normalizer; hostinger passes `BROWSER_USER_AGENT`, supabase passes its plain UA + `empty_result=None` + 30s timeout, waha `auth_header=("X-Api-Key", key) if key else None` for the `/ping` path). All `ConfirmationRequiredError`s now build via `confirmation_required_message` (byte-identical messages). Test re-points: hostinger 1 + supabase 2 urlopen-patches → `_kit.transport.urlopen` (waha 0 churn — wrapper-patched). **Cloudflare = carve-out** (its `request_envelope` attaches `cf_code` from the HTTP-error body — beyond the seam's `(message, status)` error interface; folding in would regress `cf_code`-on-HTTPError or need an N=1 seam hook). Catalogued in `KB § PATTERNS/accept-with-rationale.md`; revisit at N=2 → seam error-body hook. **Wave 3 docs:** `_kit/README.md` surface-table + § Shared HTTP transport seam (consume recipe + cloudflare exception) + Tests note (`test_http.py`); fixed a Wave-1 doc gap (transport symbols were `__init__`-exported but absent from the README table). All 6 suites green (141). Branch `feat/kit-connector-extend-wave`. | Claude |
