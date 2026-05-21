# Cloudflare API token rotation runbook

> Operational runbook — **plan only**, run by a human with explicit go/no-go per step.
> Produced 2026-05-21. At build the token slot (`mcp/cloudflare/.env`
> `CLOUDFLARE_API_TOKEN`) was **empty** — the user pastes a freshly-issued **scoped**
> token later. Cloudflare API tokens are **scoped** Bearer credentials (you choose the
> permissions); a leaked token's blast radius is whatever it was scoped to — for this
> connector that is DNS + zone + tunnel edit, which is high-impact (a leaked token can
> repoint or delete production DNS / tunnels). Hence a real rotation, not a "rotate later."

## 0 · Why this is gated, not auto-run

A Cloudflare token is a single account-wide Bearer credential (scoped to its
permissions). Issuing a new one and deleting the old is a **cutover** for every consumer
that holds it. Any consumer still on the old token starts 401ing the instant it is
revoked. Do the swap in a tight window.

## 1 · Consumer inventory (everything that holds the token)

| # | Consumer | Where the token lives | Update mechanism |
|---|---|---|---|
| 1 | **Cloudflare account** (source of truth) | dash → My Profile → API Tokens | create scoped token / roll / revoke |
| 2 | **Our Cloudflare MCP connector** | `mcp/cloudflare/.env` → `CLOUDFLARE_API_TOKEN` (gitignored) | edit file, restart MCP server |
| 3 | Any ad-hoc curl / script / CI job / Terraform using the token | various | manual sweep |

> **Pre-flight gate:** confirm row 3 is empty (no other system was handed this token).
> If anything else holds it, add it here before revoking — a revoke breaks every holder at once.

## 2 · Pre-rotation checklist

1. `cloudflare.diagnostics.connection_status` → confirm `configured ∧ reachable ∧ authenticated` (`token_status:"active"`) on the OLD token (baseline).
2. `cloudflare.zones.list` → record the zone inventory. For the zone(s) you operate, `cloudflare.dns.list_records <zone_id>` → snapshot the records (so post-rotation parity is verifiable). `cloudflare.tunnel.list` → record tunnel inventory.
3. Issue the NEW **scoped** token in dash → API Tokens with the same scopes (Zone:DNS:Edit · Zone:Zone:Read+Edit · Account:Cloudflare Tunnel:Edit). Store it in the password manager **before** use. Do NOT revoke the old one yet. (Cloudflare also supports **Roll** on an existing token — it issues a new secret for the same scopes; either path works, roll is a single-token in-place rotate.)
4. Note the old token's id/name in dash → API Tokens (you revoke it by id in §4 once green).

## 3 · Cutover sequence (tight window)

Order: stage the new token in consumers, then revoke the old one last so the gap is minimal.

1. **Stage** the new token in row 2 — edit `mcp/cloudflare/.env` `CLOUDFLARE_API_TOKEN=<new>` (leave `CLOUDFLARE_ACCOUNT_ID` unchanged — it is not a secret and does not rotate).
2. **Restart** the Cloudflare MCP server so it reloads `.env` (the settings factory is `lru_cache`d per process).
3. **Verify** (see §4) on the NEW token while the OLD token is still valid (clean rollback window).
4. Only after §4 is green: **revoke the OLD token** in dash → API Tokens, and scrub it from the password manager / any chat history / notes.

## 4 · Post-rotation verification (all must pass)

1. `cloudflare.diagnostics.connection_status` → `authenticated:true`, `token_status:"active"` on the NEW token.
2. `cloudflare.zones.list` → same zone inventory as the §2.2 baseline.
3. `cloudflare.dns.list_records <zone_id>` → same record snapshot as §2.2 (proves the DNS:Edit scope reads past Cloudflare with the new token).
4. `cloudflare.tunnel.list` → same tunnel inventory (proves the Tunnel:Edit scope).

> ⚠️ Do **NOT** use the write tools (`dns.delete_record` / `dns.update_record` /
> `tunnel.delete` / `tunnel.update_config`) to "verify" — they are real, outward-facing,
> often irreversible mutations against live production DNS / tunnels. Reads + the diagnostic
> fully prove the new token's scopes.

## 5 · Rollback

If §4 fails and you have **not yet revoked** the old token: restore `mcp/cloudflare/.env`
to the OLD token, restart the MCP server, re-verify. The old token stays valid until §3.4,
so rollback is clean — **do not revoke the old token until §4 is fully green.**

## 6 · Permanent hardening (do as part of this rotation)

- Issue the MCP connector its **own labeled, scoped** token (least privilege — only the
  DNS / Zone / Tunnel permissions it actually uses) so a future rotation is a
  single-consumer cutover and the blast radius is bounded.
- Keep the token **only** in `mcp/cloudflare/.env` (gitignored) — never inline in a script,
  a workflow node, a Terraform var file, or a committed file. If a script needs it, it reads
  the same `.env`.
- Cloudflare tokens can be **TTL-bounded** (set an expiry) and **IP-restricted** — apply both
  where the connector's host is stable; an expired/IP-bounded leaked token is far less useful.
- The first token will be **pasted in chat** when the user adds it — treat anything pasted in
  chat as compromised and rotate it once the connector is wired to its own labeled token.
