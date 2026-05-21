# `_kit` connector-boilerplate consolidation — Project Document

> **Follow-up filed per the DRY recurrence rule (N=4 → MUST formalize).** Not started. Surfaced by the Hostinger-MCP build (2026-05-21).

- **Created:** 2026-05-21
- **Status:** Filed (not started) — follow-up from `production-deploy-migration`
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
- One shared request seam + confirm-gate + settings base in `_kit`; 5 connectors consume it; all connector test suites green; no tool-surface change.

## 11. Change log
| Date | Change | By |
|---|---|---|
| 2026-05-21 | Filed from `production-deploy-migration` after Hostinger MCP flagged N=4 connector-boilerplate recurrence (+ the browser-UA-vs-CF-WAF wrinkle worth lifting) | Claude |
