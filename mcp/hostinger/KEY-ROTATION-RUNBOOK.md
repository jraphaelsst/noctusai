# Hostinger API token rotation runbook

> Operational runbook — **plan only**, run by a human with explicit go/no-go per step.
> Produced 2026-05-21. The token currently in use was **pasted in chat** (`mcp/hostinger/.env`
> header marks it TEMP), so it MUST be rotated to a freshly-issued token. Hostinger API
> tokens are **account-scoped Bearer tokens** with broad reach (VPS power actions,
> domains, billing) — a leaked token is high-blast-radius, hence a real rotation, not a
> "rotate later."

## 0 · Why this is gated, not auto-run

A Hostinger token is a single account-wide Bearer credential. Issuing a new one and
deleting the old is a **cutover** for every consumer that holds it. Any consumer still on
the old token starts 401ing the instant it is revoked. Do the swap in a tight window.

## 1 · Consumer inventory (everything that holds the token)

| # | Consumer | Where the token lives | Update mechanism |
|---|---|---|---|
| 1 | **Hostinger account** (source of truth) | hPanel → API (the issued token list) | issue new token / revoke old token |
| 2 | **Our Hostinger MCP connector** | `mcp/hostinger/.env` → `HOSTINGER_API_TOKEN` (gitignored) | edit file, restart MCP server |
| 3 | Any ad-hoc curl / script / CI job using the token | various | manual sweep |

> **Pre-flight gate:** confirm row 3 is empty (no other system was handed this TEMP token).
> If anything else holds it, add it here before revoking — a revoke breaks every holder at once.

## 2 · Pre-rotation checklist

1. `hostinger.diagnostics.connection_status` → confirm `configured ∧ reachable ∧ authenticated` on the OLD token (baseline).
2. `hostinger.vps.list` → record the VM inventory + each VM's `state` (so post-rotation parity is verifiable).
3. Issue the NEW token in hPanel → API. Store it in the password manager **before** use. Do NOT revoke the old one yet.
4. Note the old token's id/label in hPanel (you revoke it by id in §4 once green).

## 3 · Cutover sequence (tight window)

Order: stage the new token in consumers, then revoke the old one last so the gap is minimal.

1. **Stage** the new token in row 2 — edit `mcp/hostinger/.env` `HOSTINGER_API_TOKEN=<new>`. Do not restart yet if you want to verify the old one is still live first; otherwise restart now.
2. **Restart** the Hostinger MCP server so it reloads `.env` (the settings factory is `lru_cache`d per process).
3. **Verify** (see §4) on the NEW token while the OLD token is still valid (clean rollback window).
4. Only after §4 is green: **revoke the OLD token** in hPanel → API, and scrub it from the password manager / any chat history / notes.

## 4 · Post-rotation verification (all must pass)

1. `hostinger.diagnostics.connection_status` → `authenticated:true` on the NEW token.
2. `hostinger.vps.list` → same VM inventory + states as the §2.2 baseline.
3. `hostinger.vps.get <id>` for the production VM (`1303151`) → `state:"running"` (unchanged — rotation never touches VM power).
4. `hostinger.vps.metrics <id>` with a recent `date_from`/`date_to` window → returns series (proves a read past Cloudflare with the new token).

> ⚠️ Do **NOT** use `hostinger.vps.stop`/`start`/`restart` to "verify" — they are real power
> actions against a running production box. Reads + the diagnostic fully prove the new token.

## 5 · Rollback

If §4 fails and you have **not yet revoked** the old token: restore `mcp/hostinger/.env` to
the OLD token, restart the MCP server, re-verify. The old token stays valid until §3.4, so
rollback is clean — **do not revoke the old token until §4 is fully green.**

## 6 · Permanent hardening (do as part of this rotation)

- The TEMP token was pasted in plaintext in chat — treat it as compromised; the rotation
  above is mandatory, not optional.
- Keep the token **only** in `mcp/hostinger/.env` (gitignored) — never inline in a script,
  a workflow node, or a committed file. If a script needs it, it reads the same `.env`.
- Hostinger tokens can be **scoped/labeled** per use — issue the MCP connector its own
  labeled token so a future rotation is a single-consumer cutover (narrows blast radius).
