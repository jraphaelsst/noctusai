# Feature — n8n + WhatsApp notifications (verify + parity-gate)

> **What this is.** Wiring the n8n connector live, verifying the n8n + WhatsApp (WAHA)
> notification path, and the recommended automation pair from the 2026-05-22 `findings.md`
> session: **#1 prod-config parity gate** (prevention) + **#4 fleet-health → WhatsApp** (detection).
>
> - **Created:** 2026-05-23 · **Owner:** rapha · **Branch:** `feat/seed-deploy-config-contract`
> - **Trigger:** user — "what automations could I dev re: last findings" → recommended prevent+detect pair.

---

## 0. Status (what's already done, restart-independent)

| Item | State |
|---|---|
| n8n key stored | ✅ `mcp/n8n/.env` (`N8N_BASE_URL=https://n8n.noctusai.com` + `N8N_API_KEY`), gitignored (`.gitignore:13`) |
| n8n live | ✅ curl `GET /api/v1/workflows` → 200, 10 workflows visible |
| n8n MCP **in-session** | ⏳ `configured:false` — settings are process-cached; **needs a Claude Code restart** to reload `mcp/n8n/server.py` |
| WAHA live | ✅ `waha.diagnostics.connection_status` → configured + reachable + authenticated, 1 session |
| Connector unit tests | ✅ `44 passed` (n8n + waha suites) |
| WhatsApp test-send | ✅ sent to `5511974693365@c.us` 2026-05-23 (msg `…3EB03242AA969D6D609BFA`, via WAHA MCP — `IsFromMe=true`) |
| **#4 health→WhatsApp** | ⚠️ the only impl (`UptimeRobot - Alerta WhatsApp`) was an **UNUSED** 2-node stub → **DELETED** 2026-05-23 per user (snapshot `/tmp/uptimerobot-alerta-whatsapp.workflow.json`). Health→WhatsApp is now **UNBUILT** — see §3. |
| **#1 parity gate** | ✅ **BUILT 2026-05-23** — `prod_config_parity` check + `audit_prod_config_parity` in `predeploy_check.py` (the deploy-config-contract 3rd leg). 35 tests pass. See §4. |
| Chatbot multi-bubble delivery | ✅ **shipped to the seed** 2026-05-23 — see §6 |

WhatsApp accounts: alerts **to** `5511974693365@c.us` (personal), sent **from** `5511992694172@c.us` (the "One Chat" WAHA session). **No auto-send** — outward sends require an explicit user-named target.

---

## 1. Live verification — curls (restart-independent)

```bash
cd /Users/rapha/Documents/repository/NoctusAI/noctusai

# --- n8n connectivity (proven: 200) ---
set -a; . mcp/n8n/.env; set +a
curl -sS -H "X-N8N-API-KEY: $N8N_API_KEY" "$N8N_BASE_URL/api/v1/workflows?limit=1" -o /dev/null -w "n8n: HTTP %{http_code}\n"

# --- WAHA send shape (what the n8n node calls). Fill YOUR number. ---
set -a; . mcp/waha/.env; set +a   # WAHA_BASE_URL + WAHA_API_KEY (verify var names)
curl -sS -X POST "$WAHA_BASE_URL/api/sendText" \
  -H "X-Api-Key: $WAHA_API_KEY" -H "Content-Type: application/json" \
  -d '{"session":"default","chatId":"<YOUR_NUMBER>@c.us","text":"noc test ✅"}'

# --- E2E: trigger the EXISTING UptimeRobot→WhatsApp chain (sends a real alert) ---
curl -sS -X POST "$N8N_BASE_URL/webhook/uptime-alert" -H "Content-Type: application/json" \
  -d '{"body":{"monitorFriendlyName":"TEST — ignore","alertTypeFriendlyName":"Down (test)"}}'
```

## 2. Tests

```bash
cd /Users/rapha/Documents/repository/NoctusAI/noctusai
PYTHONPATH=mcp mcp/noctusai/.venv/bin/python -m pytest mcp/n8n/tests mcp/waha/tests -q   # → 44 passed
```
Canonical connectivity check (post-restart) is the MCP diagnostic, not a script:
`n8n.diagnostics.connection_status` · `waha.diagnostics.connection_status`.

---

## 3. Finding — #4 was an UNUSED stub, now DELETED (rebuild if wanted)

**Corrected 2026-05-23.** The workflow `UptimeRobot - Alerta WhatsApp` (`id=zmC_W1GVICNRN4IJTHOJl`)
existed as a 2-node `Webhook(uptime-alert) → HTTP POST waha.noctusai.com/api/sendText` chain
(created 2026-01-29, last touched 2026-05-19). It was **never actually wired** to UptimeRobot
(no monitor POSTed to it) → user confirmed "useless" and authorized deletion. I snapshotted it
(`/tmp/uptimerobot-alerta-whatsapp.workflow.json`, 4625 B) and **deleted** it (DELETE 200,
get-after-delete 404).

**So fleet-health→WhatsApp is currently UNBUILT.** If wanted, the fresh agent should build a
*real* one: a webhook (or scheduled `noctus.vps.health` poll) → WAHA `send_text`, with **coverage**
over the live fleet roster (`noctus.dev.list_products` / `agent_context`). The connectors are
proven (see §1/§2); only the workflow + the monitor wiring are missing.

> The other 9 workflows are real ERP automations (Certidões/Matrícula/SDR/CNPJ) + the
> **`SDR Agent` family** (`SDR Agent Template` 36 nodes, `SDR Agent` 39, `SDR Agent copy` 30) —
> the template the chatbot lift (§6) was inspired by. Leave all untouched.

---

## 4. #1 — prod-config parity gate — ✅ BUILT 2026-05-23

**Status: DONE.** Implemented during the discovery that this branch (`feat/seed-deploy-config-contract`)
already ships the deploy-config-contract — the `noctusai_lib.config.deploy_config` boot guard +
the static `check_derives_from_dev_only_artifact` keeper. The parity gate is the **3rd leg**:
*pre-deploy value-correctness*. The boot guard only checks key **presence** — a present-but-localhost
value (`PRODUCT_URL_CORE=http://localhost:8000`) passes it but is exactly the ARC1/ARC2 drift; this
gate catches it.

**Shipped:** `prod_config_parity` (default check in `noctus.dev.predeploy_check`) + the pure auditor
`audit_prod_config_parity(roster_slugs, env)` (`mcp/noctusai/tools/noctus/dev/predeploy_check.py`).
- (1) every product in the live roster (`parse_products_registry`, never frozen) resolves a prod URL
  without DB-localhost fallthrough (`PRODUCT_URL_<SLUG>` ∨ `PRODUCT_URL_PATTERN`);
- (2) no `PRODUCT_URL_*`/`CORS_ORIGINS` value carries a loopback host (`localhost`/`127.0.0.1`/`0.0.0.0`/`::1`).
- Snapshot source (option **b**, deterministic): explicit `prod_env_path` → `NOCTUS_PROD_ENV_FILE`
  → a PROD-named file (`.env.prod`/`.env.production`). The dev `.env` is **excluded** (carries
  localhost by design). No snapshot ⇒ a LOUD skip, never a silent pass.
- Failures classify as `prod_config_localhost` (B4 container env). 11 colocated tests (suite **35 passed**).
- Three-way-synced: `KB § PATTERNS/deploy-config-contract.md § 5b`, `boundary-contract-tests.md` B4 row,
  memory `project_prod_config_parity_gate.md`.

**Future hook (NOT built):** option (a) — a live VPS `.env` cross-check over the `noctus.vps.*` SSH path.

**Surfaced finding (not fixed — out of scope):** `deploy-config-contract.md` and the memory
`feedback_dev_prod_parity_verify_in_prod_shape` both reference `KB § PATTERNS/dev-prod-parity.md`,
which does NOT exist yet (a `[[dev-prod-parity]]` dangling wikilink). That doc is owned by the
in-flight `seed-deploy-config-contract` project — flag it at that project's reconciliation.

---

### Original spec (kept for provenance)

**Goal:** block a deploy when the prod env would reproduce the ARC 1/2 drift (nav→localhost,
CORS localhost-only). **The platform's #1 recurrence class.**

**Shape:** extend `mcp/noctusai/tools/noctus/dev/predeploy_check.py` (don't invent a parallel tool).
It already has `_KNOWN_BOUNDARIES`, `classify_failure()`, per-check fns, `_render_report()`,
`predeploy_check()` (the entry, L249), `register()`. Mirror the existing **D3 `deploy_local_gitignored`**
check (L49) — it's the template for a new boundary check.

**New check `prod_config_parity`** asserts, for every live product in the roster:
- `PRODUCT_URL_<SLUG>` present **or** `PRODUCT_URL_PATTERN` set (no fallthrough to DB localhost);
- CORS-deriving vars present (the `derive_cors_origins` inputs — `PRODUCT_URL_*`);
- **no `localhost`/`127.0.0.1`** in any value destined for a prod origin.

**Decision to make with the user:** source of the prod env —
(a) read the VPS `.env` over SSH (reuse the `noctus.vps.*` SSH path), or
(b) operate on a provided snapshot / `.env.example` required-keys manifest.
(a) is truer to prod; (b) is hermetic/testable. Recommend (b) for the gate's deterministic core
+ an optional (a) live cross-check.

**Must ship:** colocated test (`mcp/noctusai/tests/...`) per regression-test-the-detector;
roster derived via `parse_products_registry()` (never a frozen slug list); three-way-sync if it
graduates to a rule (KB + CLAUDE.md + memory).

---

## 5. Handoff to fresh agent
Restart Claude Code first (reloads the n8n MCP — currently `configured:false`, process-cached),
then: confirm `n8n.diagnostics.connection_status` green → **build #1** (§4 parity gate) →
optionally **(re)build #4** (§3 — health→WhatsApp, the old stub is gone). CF connector
registration is **not** approved yet (leave `.mcp.json` as-is).

---

## 6. Chatbot multi-bubble delivery — SHIPPED to the seed (2026-05-23)

User shared the n8n **SDR Agent Template** and asked: do we already have its two tricks, and can
we improve our chatbot methodology with it?

| SDR technique | Was in noc? | Now |
|---|---|---|
| Redis queue / debounce (Passo 03) | ✅ already in the seed (`ConversationBufferService` + `ConversationWorker`) | unchanged (more robust than the template) |
| Split long reply → multiple bubbles + delay (Passo 04+05) | ⚠️ only a social-wiring fork (`whatsapp_outbound.py`) | ✅ **lifted to the seed** |

**Shipped:** `noctusai_lib.domain.chatbot.delivery` → `split_reply` + `send_reply_parts` (async)
+ `send_reply_parts_sync` (sync), channel-neutral via a `send_one(part)` seam. social-wiring's
`whatsapp_outbound.py` is now a thin `settings`-binding shim over the seed (callers + its 10 tests
unchanged). Seed tests `seed/lib/backend/tests/domain/chatbot/test_delivery.py` (16 cases) —
**seed suite 92 passed, social-wiring shim 10 passed.** KB wiring-recipe + memory updated
(three-way-sync). Recipe now teaches multi-bubble instead of a single wall-of-text.

**v2 (not built):** typing/presence indicator (`startTyping`/`sendSeen`) between bubbles.
