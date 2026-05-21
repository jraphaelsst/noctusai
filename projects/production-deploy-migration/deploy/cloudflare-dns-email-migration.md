# Cloudflare NS migration + domain email (`jraphaelsst@noctusai.com`)

Runbook for moving `noctusai.com` DNS from **name.com → Cloudflare** and then
adding **Cloudflare Email Routing** (forward `jraphaelsst@noctusai.com` →
`joaoraphaelsst@gmail.com`). Written 2026-05-21.

The NS move is the shared prerequisite for BOTH email routing AND the named
tunnel (`deploy/tunnel/`). This runbook does the **behavior-preserving NS move +
email**; the tunnel cutover stays a SEPARATE later step (one change at a time).

> **Why a domain alone gives you no email:** registering `noctusai.com` only
> reserves the name. An inbox needs (1) a mailbox host + (2) **MX** records that
> tell the world where to deliver mail. Today `noctusai.com` has **zero MX
> records**, so the address does not exist yet — we are *creating* it.

---

## Source-of-truth inventory (LIVE name.com zone, snapshot 2026-05-21)

Captured via `dig`. This is the checklist the Cloudflare zone MUST match
**before** the nameserver flip. Verified by probing every subdomain in the repo
— blanks below have no live record (aspirational only, do NOT copy).

| Type | Name | Value | Points to | CF proxy setting |
|---|---|---|---|---|
| A | `noctusai.com` (apex) | `72.61.28.36` | VPS / Caddy → core | **DNS-only (grey)** |
| TXT | `noctusai.com` | `replit-verify=bee5257b-b67c-4f17-9947-2b55c3d3ef4c` | Replit ownership | — |
| TXT | `_dmarc.noctusai.com` | `v=DMARC1; p=reject; sp=reject; pct=100;` | anti-spoof policy | — |
| A | `core.noctusai.com` | `72.61.28.36` | VPS / Caddy | **DNS-only (grey)** |
| A | `erp.noctusai.com` | `72.61.28.36` | VPS / Caddy | **DNS-only (grey)** |
| A | `social.noctusai.com` | `72.61.28.36` | VPS / Caddy | **DNS-only (grey)** |
| A | `n8n.noctusai.com` | `72.61.28.36` | VPS / Caddy | **DNS-only (grey)** |
| A | `waha.noctusai.com` | `72.61.28.36` | VPS / Caddy | **DNS-only (grey)** |
| A | `legacy.noctusai.com` | `72.61.28.36` | VPS / Caddy | **DNS-only (grey)** |

No `AAAA`, no `CAA`, no `www`, no `MX`. Current NS: `ns{1cny,2ckr,3jkl,4hny}.name.com`.

**🔴 The grey-cloud rule is non-negotiable here.** All 7 VPS hosts (apex +
core/erp/social/n8n/waha/legacy) run **Caddy with its own Let's Encrypt
HTTP-01** TLS. If Cloudflare proxies them (orange cloud — CF's *default* when it
auto-imports), CF intercepts port 80 → Caddy's cert renewal fails → TLS errors.
So **all records = DNS-only / grey cloud**. We are only changing *who answers
DNS*, not how any site is served.

**Notable for email:** the existing `_dmarc` is `p=reject`. That governs mail
*sent AS* `@noctusai.com` (Phase 3), not mail *received* — inbound forwarding via
CF uses SRS so the original sender's SPF/DMARC still aligns at Gmail. Receiving
is unaffected by the reject policy.

---

## Ordering — the one thing that must not go wrong

```
Phase 0 (populate CF zone, grey-cloud)  ──MUST COMPLETE──►  Phase 1 (Replit flips NS)
```

⚠️ **Replit has already been asked to flip the nameservers.** If they flip
*before* the CF zone is a complete grey-cloud mirror of the table above, the live
site (apex on Replit + 6 VPS subdomains) goes dark until the zone is fixed.
**Confirm Phase 0 is done & verified before Replit performs the change** — if
they're quick, ask them to hold until we say go.

---

## Phase 0 — mirror the zone into Cloudflare (behavior-preserving) — DO BEFORE FLIP

When the domain was added to Cloudflare, CF auto-imported the existing records.
That import is **not trustworthy**: it can miss records and it defaults A/CNAME
to **proxied (orange)**. So Phase 0 is *verify + correct*, not blind trust.

1. In the CF zone for `noctusai.com`, confirm **all 9 rows** in the table exist,
   values exact.
2. Set **every A record to DNS-only (grey cloud)**. Re-check after — CF sometimes
   re-proxies on edit.
3. Add anything the import missed (the `_dmarc` TXT and `replit-verify` TXT are
   the usual casualties).
4. Do **not** add `www` / other subdomains — they have no live record today;
   adding them would change behavior.

Verification (run against CF's nameservers directly, before the flip):
```bash
# replace with the two CF nameservers CF assigned you
CF_NS=<one-of-your-cloudflare-nameservers>
for h in noctusai.com core.noctusai.com erp.noctusai.com social.noctusai.com \
         n8n.noctusai.com waha.noctusai.com legacy.noctusai.com; do
  echo "$h -> $(dig +short @$CF_NS A $h)"
done
dig +short @$CF_NS TXT _dmarc.noctusai.com
dig +short @$CF_NS TXT noctusai.com
```
All 7 hosts (apex + 6 subdomains) must return `72.61.28.36`; both TXTs present.

---

## Phase 1 — the nameserver flip (BLOCKED on Replit)

> **Update 2026-05-21:** Replit support replied with a **registrar-transfer
> authorization (EPP/auth code)** — *not* an NS change (their self-serve UI does
> records + disconnect only). But Cloudflare Registrar won't accept a transfer
> until the zone is **Active** (NS already on CF), so the NS repoint is the
> prerequisite *either way*. **The ask to Replit is therefore the NS change to
> `clyde.ns.cloudflare.com` + `lina.ns.cloudflare.com`** (the two CF nameservers
> this zone was assigned; zone status is currently `pending`). The EPP transfer
> is the *optional* follow-up to also move the registration to CF (full
> "only-CF"). Also note the **apex A-record has already been repointed to the
> VPS** (`72.61.28.36`, Caddy → core), so the apex no longer stays on Replit
> during the interim — when the zone goes Active, mirror apex → `72.61.28.36`.

Replit changes NS at name.com from `ns*.name.com` → the two Cloudflare
nameservers. Then:

- Propagation: minutes to ~24–48h. Because Phase 0 made CF an exact mirror,
  there is **no downtime window** — resolvers seeing either NS get identical
  answers.
- Verify after CF shows the zone "Active":
  ```bash
  dig +short NS noctusai.com                       # should show *.ns.cloudflare.com
  curl -I https://core.noctusai.com/api/health     # still 200 via Caddy
  curl -I https://noctusai.com                      # apex served by Caddy -> core on the VPS
  ```

---

## Phase 2 — Cloudflare Email Routing (RECEIVE) — after the flip, additive & safe

Zone must be Active on CF first. This only *adds* records; it can't break the site.

1. CF dashboard → **Email** → **Email Routing** → **Enable**. CF auto-adds:
   - 3 MX: `route1/2/3.mx.cloudflare.net`
   - 1 SPF TXT: `v=spf1 include:_spf.mx.cloudflare.net ~all`
2. **Destination addresses** → add `joaoraphaelsst@gmail.com` → CF emails it a
   confirmation link → click it. (Gmail must confirm before it can receive.)
3. **Routing rules** → custom address `jraphaelsst@noctusai.com` → action
   *Send to* `joaoraphaelsst@gmail.com`.
   - Optional: **Catch-all** → same Gmail, so any `*@noctusai.com` also lands.
4. Test: from another account, email `jraphaelsst@noctusai.com` → it appears in
   `joaoraphaelsst@gmail.com`. Verify:
   ```bash
   dig +short MX noctusai.com     # route1/2/3.mx.cloudflare.net
   ```

After this, **receiving works.** This is the milestone the request asked for.

---

## Phase 3 — sending AS `jraphaelsst@noctusai.com` (OPTIONAL, later)

CF Email Routing is **forward-only — it cannot send.** To reply *as*
`jraphaelsst@noctusai.com` from Gmail you need an SMTP path, and because the
domain's DMARC is `p=reject`, that path must have **aligned SPF + DKIM** or
recipients will reject the mail. Two routes:

- **Gmail "Send mail as" + an SMTP relay** — add SPF/DKIM for the relay to the CF
  zone, configure Gmail Settings → Accounts → "Send mail as". More moving parts.
- **Google Workspace (~$6/mo)** — native send, auto SPF/DKIM, full Gmail UI on
  the domain. **Switching here later is fully supported**: swap MX from CF →
  Google + add Google's verify TXT + DKIM. CF routing now does NOT lock you out
  of Workspace later (mail host = MX records = swappable any day). The only
  caveat: don't create a *consumer/free* Google login on `jraphaelsst@noctusai.com`
  in the meantime (avoids a "conflicting account" to untangle at Workspace onboarding).

Deferred until sending is actually needed. Receiving (Phase 2) stands alone.

---

## What needs CF API access (so the agent can execute Phase 0)

**Status 2026-05-21:** `mcp/cloudflare/.env` now holds a **working** scoped
`CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` (token verified `active`). The
zone for `noctusai.com` already exists on CF — status **`pending`**, CF
nameservers **`clyde.ns.cloudflare.com` + `lina.ns.cloudflare.com`** — and goes
*Active* the moment the registrar repoints NS to those two. Phase 0 can run via
the API (token scoped **Zone → DNS Edit** + **Zone → Read**) or by hand in the
dashboard. The connector itself stays user-gated in `.mcp.json` (MCP keep-list).
