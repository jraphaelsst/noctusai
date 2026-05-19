# WAHA `X-Api-Key` rotation runbook

> Operational runbook — **plan only**, run by a human with explicit go/no-go per step.
> Produced 2026-05-19. The key currently in use was found hard-coded in plaintext
> inside an n8n workflow definition (`UptimeRobot - Alerta WhatsApp`), which is why
> rotation is warranted. This is **outward-facing and hard-to-reverse**: a botched
> rotation silently breaks live WhatsApp alerting + the Matrícula document flow.

## 0 · Why this is gated, not auto-run

WAHA exposes a **single** `WHATSAPP_API_KEY` (no multi-key/grace-period support in
the CORE tier). So rotation is a **cutover**, not an add-then-revoke. Every consumer
must flip in a tight window or it 401s. Do this in a low-traffic window.

## 1 · Consumer inventory (everything that holds the old key)

| # | Consumer | Where the key lives | Update mechanism |
|---|---|---|---|
| 1 | **WAHA server** (source of truth) | `WHATSAPP_API_KEY` env on the WAHA container (`docker-compose.infra.yml` / its `.env`) | redeploy container with new env |
| 2 | **Our WAHA MCP connector** | `mcp/waha/.env` → `WAHA_API_KEY` (gitignored) | edit file, restart MCP server |
| 3 | **n8n — UptimeRobot - Alerta WhatsApp** (`zmC_W1GVICNRN4IJTHOJl`, ACTIVE) | **hard-coded inline** in the `Enviar WhatsApp` httpRequest node `X-Api-Key` header | `n8n.workflow.get` → replace value → `n8n.workflow.update(confirm=true)` **OR** (preferred) move to an n8n credential via `n8n.credential.create` + reference it |
| 4 | **n8n — `wahaApi` credential** (`id 55X1m6M4D2yehbWf`) | n8n-stored credential, referenced by `EnviaMsg` in Matrícula + both SDR Agents | n8n UI → edit credential (no public-API credential-update; `n8n.credential.create` a replacement + repoint, or edit in UI) |
| 5 | **The chatbot's WAHA** | ⚠️ `mcp/waha/.env` header note says *"This file differs from the Waha the Chatbot consumes."* | **CONFIRM FIRST** whether the chatbot points at the same WAHA host/key. If different instance → out of scope for this rotation. If same → add to this list. |
| 6 | WAHA dashboard / any ad-hoc curl, UptimeRobot monitor configs, etc. | various | manual sweep |

> **Pre-flight gate:** resolve row 5 before touching anything. If the chatbot shares
> this WAHA + key, a rotation here takes the chatbot down too — that widens the blast
> radius and the window must be coordinated with the chatbot owner.

## 2 · Pre-rotation checklist

1. `waha.diagnostics.connection_status` → confirm `configured ∧ reachable ∧ authenticated` on the OLD key (baseline).
2. `waha.session.get` → record current session status (expect `WORKING`).
3. Generate the new key: `openssl rand -hex 24` → prefix to match convention (`noct-…`). Store in the password manager **before** use.
4. Snapshot the UptimeRobot workflow: `n8n.workflow.get zmC_W1GVICNRN4IJTHOJl` → save JSON (rollback).
5. Announce the maintenance window (alerting + Matrícula inbound will be briefly unavailable).

## 3 · Cutover sequence (tight window, ideally <2 min)

Order matters: update **consumers first**, server **last**, so the gap is minimal.

1. **Stage** new key in every consumer WITHOUT activating:
   - Row 2: edit `mcp/waha/.env` (don't restart yet).
   - Row 3: prepare the `n8n.workflow.update` payload (don't send yet) — or pre-create the n8n credential with the new key (row 4 mechanism), leaving the workflow still pointing at the old one.
   - Row 4: `n8n.credential.create` a NEW `httpHeaderAuth`/WAHA credential carrying the new key (use `n8n.credential.schema` to get the type's required fields). Do **not** delete the old credential yet.
2. **Flip the WAHA server** (row 1): redeploy the WAHA container with `WHATSAPP_API_KEY=<new>`. From this instant the old key 401s.
3. **Immediately activate** all consumers:
   - Row 2: restart the WAHA MCP server (so it reloads `.env`).
   - Row 3: `n8n.workflow.update(confirm=true)` with the new key / new credential reference.
   - Row 4: repoint `EnviaMsg` in Matrícula + both SDR Agents to the new credential (`n8n.workflow.update(confirm=true)` each). Matrícula is ACTIVE — `get` snapshot first.
4. **Verify** (see §4). Only after green: delete the old n8n credential and scrub the old key from the password manager / any notes.

## 4 · Post-rotation verification (all must pass)

1. `waha.diagnostics.connection_status` → `authenticated:true` on the NEW key.
2. `waha.session.get` → still `WORKING` (rotation doesn't touch the WhatsApp session, but confirm).
3. `waha.message.send_text(confirm=true)` a test message to your own number → delivered.
4. Trigger an UptimeRobot test alert (or replay its webhook) → message arrives (proves row 3).
5. Send a test document to the Matrícula WhatsApp → flow runs to completion (proves row 4 credential).
6. `n8n.execution.list status=error` for the touched workflows → no NEW 401/auth errors.

## 5 · Rollback

If §4 fails: redeploy the WAHA server with the OLD `WHATSAPP_API_KEY`, restore
`mcp/waha/.env`, `n8n.workflow.update` the UptimeRobot workflow from the §2.4
snapshot, repoint credentials back. The old key remains valid until step §3.4, so
rollback is clean if you have not yet deleted it — **do not delete the old key /
credential until §4 is fully green.**

## 6 · Permanent hardening (do as part of this rotation)

- Row 3 should end with the key in an **n8n credential**, never inline again
  (`n8n.credential.create` now exists for exactly this — see `KB § MCP-SERVERS/n8n.md`).
- Same for the pdf.co key hard-coded in `Matrícula Extractor Agent` (`HTTP Request2`,
  `Upload File`) and the Vista `key=` query param in `SDR Agent` — out of scope for the
  *WAHA* rotation but the same anti-pattern; rotate + externalize them on the same pass
  if convenient.
