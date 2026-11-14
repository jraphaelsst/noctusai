# Roadmap · Unsigned-webhook fail-closed rollout — 2026-11

**Slug:** `unsigned-webhook-rollout` · **Approved by the owner 2026-11-05** ("approve the webhook rollout, start with the secret inventory") · **Finding:** WE-2 in `KB § PATTERNS/security/appsec-craft-canon.md` (P0, CVSS 4.0 8.2) · **Mechanism:** `seed/lib/backend/noctusai_lib/security/webhook_signatures.py` (`WEBHOOK_REQUIRE_SIGNATURE`, `bypass_when_unset`)

## Goal
Every inbound webhook in a live product refuses unsigned traffic, with no receiver going dark. The order is fixed:
1. inventory (this file, §2);
2. provision the missing secrets and confirm each sender signs;
3. `WEBHOOK_REQUIRE_SIGNATURE=1` per product;
4. flip the seed default last.

Steps 2–4 are deploys. They go to the CI/deploy steward as SHIP-REQUESTs.

## Status legend
`[x]` done · `[~]` in flight · `[ ]` open · `[owner]` owner decision · `[steward]` steward-only step

## 1 · Phases
- [x] **P1 · Inventory** (2026-11-05, read-only): call sites on `origin/dev`, plus the prod container env read with `docker inspect`. Presence and length only; no value was read. §2 below.
- [ ] **P2 · Provision + sender check.** For each fail-open row with a gap: set the secret in the root `.env`, recreate, and confirm the sender signs with the same key (hash/length compare only).
- [ ] **P3 · Per-product flag.** Set `WEBHOOK_REQUIRE_SIGNATURE=1` for each live product whose rows are all green. Order: monica → seed → social-wiring → orbity.
- [ ] **P4 · Flip the seed default** to refuse in a deploy context. Only after P3 holds a week with no 401 storm. The first attempt failed batch `mq-candidate/42047199280-2`, which is why this order exists.

## 2 · Inventory (2026-11-05)

How prod gets secrets: every product container loads the root `.env` through `env_file:` (`deploy/fleet/docker-compose.prod.yml`). The containers have no mounts, so `docker inspect` `.Config.Env` is authoritative. A container keeps the env it was created with: a key added to the root `.env` reaches a product only when that product is recreated.

Live scope (`deploy/fleet/active-scope.txt`): agents, core, monica, orbity, seed, social-wiring.

### 2.1 Fail-open mounts in live products (they change behaviour under P3/P4)
| Product | Mount | Secret source | Prod state | Sender signs? | Gap |
|---|---|---|---|---|---|
| monica | `products/nosnolimiar/backend/app/routers/whatsapp_router.py` → seed `create_whatsapp_inbox_router` (scheme `waha`, bypass on unset) | `MONICA_WAHA_WEBHOOK_HMAC_SECRET` | SET (64) | Monica's own WAHA has `WHATSAPP_HOOK_HMAC_KEY` SET (64); key equality not checked | Ready, pending an equality check |
| social-wiring | `products/social-wiring/backend/app/routers/whatsapp_router.py` token route (scheme `waha`, bypass on unset) | `WAHA_WEBHOOK_HMAC_SECRET` | SET (64), container created 2026-11-05 | Shared WAHA: `NOC-REMEDIATE[waha-hmac-prod]` says it doesn't sign; no rejection lines in the last 24h of logs | Confirm the shared WAHA session's signing key |
| orbity | `products/orbity/backend/app/routers/whatsapp_webhook_router.py` (hand-rolled `verify_waha_hmac`, accepts unsigned when unset) | `WAHA_WEBHOOK_HMAC_SECRET` | **ABSENT**: container created 2026-11-04, before the key reached the root `.env` | Unknown | 🔴 The next recreate turns verification on. It's a steward hard gate: confirm the sender key first |
| seed | `products/seed/backend/app/routers/webhook_router.py` example route (svix, bypass on unset) | `EXAMPLE_WEBHOOK_SECRET` | ABSENT | n/a (example) | Refusing is the desired end state; no provisioning |
| agents, core | none found | — | — | — | — |

### 2.2 Already fail-closed in live products (`bypass_when_unset=False`): unaffected by P3/P4, but a missing secret means the receiver answers 401 today
| Mount | Secret source | Prod env | Note |
|---|---|---|---|
| `products/social-wiring/backend/app/modules/email_marketing/routers/webhooks.py` (Resend, svix) | `RESEND_WEBHOOK_SECRET` | ABSENT | Resend delivery events are refused. Provision or confirm the route is unused |
| `products/social-wiring/backend/app/modules/meta_ads/routers/leadgen_router.py` | Meta App Secret via `app_config_store.resolve_meta_app_creds` (DB first) | `META_APP_SECRET` ABSENT in env | Check the DB row |
| `products/social-wiring/backend/app/modules/portal_leads/routers/imovelweb_webhook.py` | `get_imovelweb_config().webhook_secret` (DB first, env fallback) | not in env | Check the DB row |
| `products/social-wiring/backend/app/modules/portal_leads/routers/olx_webhook.py` (both routes) | `get_olx_config().webhook_secret` (DB first, env fallback) | not in env | Check the DB row |

### 2.3 Outside live scope (asleep per the catalog; not touched by this rollout until woken)
- **igig**: running, but not in active-scope. `products/igig/backend/app/routers/lead_webhooks_router.py` WAHA route is fail-open on `IGIG_WAHA_WEBHOOK_HMAC_SECRET` (ABSENT). Its Meta leadgen and `products/igig/backend/app/routers/comercial_router.py` signature routes are fail-closed on `IGIG_META_APP_SECRET` (per-page DB secret first) and `IGIG_ASSINATURA_WEBHOOK_SECRET` (ABSENT).
- **commerce**: running, not in active-scope; same example svix route as seed.
- **erp-imobiliario**: not running; `products/erp-imobiliario/backend/app/routers/meta_api.py` is fail-closed; `products/erp-imobiliario/backend/app/routers/whatsapp_webhook.py` is fail-open on a per-session DB secret.
- **community**: not running; hand-rolled `verify_waha_hmac`, accepts unsigned when `COMMUNITY_WAHA_WEBHOOK_HMAC_SECRET` is unset.
- **seed library, not mounted by a live product route found**: `seed/lib/backend/noctusai_lib/integrations/whatsapp/router.py` (`handle_unsigned_webhook`), `seed/lib/backend/noctusai_lib/integrations/payments/webhook_events.py` (basic shared secret), and `seed/lib/backend/noctusai_lib/integrations/signature/real.py` (HMAC under the provider key).

## 3 · Open checks (named owners)
- [steward] Orbity sender-key check before its next recreate. igig and commerce have the same shape and get checked at their next deploys. Recorded by noctusai-51 on 2026-11-05.
- [ ] Equality check of the sender key for monica and the shared WAHA (hash compare, never print). Steward or owner, since it reads secret material.
- [ ] Decide `RESEND_WEBHOOK_SECRET` (provision vs route unused) and check the DB rows for Meta leadgen, ImovelWeb and OLX. integrations-engineer, read-only first.
