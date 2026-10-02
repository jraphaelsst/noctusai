# Roadmap — store launch (2026-10)

> Milestone bullets get ✅ only when genuinely reached. `M5` is the prod-promotion milestone referenced by `deploy/consent/store.prod.yml` (`KB § PATTERNS/devops/prod-exposure-consent.md`).

## Origin

On 2026-10-02 the owner asked to sell the generic "Contrato de Compra e Venda de Imóvel" (people ask Gilson for it on Instagram) as a digital product: a sales landing page in the Store Visual Identity, Asaas checkout, and a `/login` (no visible button) to edit the page's values. Owner decisions: `store.noctusai.com` first (own domain later), delivery by email + thank-you page, admin = only the owner, price R$ 47.

Contract: `products/store/projects/store-v1-CONTRACT.md`.

## Milestones

- **M1: scaffold** — seed-first scaffold, core catalog-row migration, contract. ✅ reached 2026-10-02 (`21a013b32`).
- **M2: seed one-off checkout** — `integrations.payments` one-off charge (Fake + Asaas + Stripe + factory), lifted from p-studio's product-local `criar_cobranca`. ✅ reached 2026-10-02 (117 seed payments tests).
- **M3: store BE + FE** — public landing, `/obrigado`, checkout, webhook fulfillment (email + signed download), `/admin` settings + sales; tests green; `predeploy_check` ready. ✅ reached 2026-10-02 — keys in the DB via the seed api-keys seam (owner directive), no monkeypatching in store tests, backend 152 + frontend 28 green, `predeploy_check store` = ready (12/12) on the integrated dev tip, migrations 001–009 applied, kit uploaded to the private bucket, local browser check of landing / checkout dialog / `/obrigado` against the live DB.
- **M4: Asaas sandbox end-to-end** — a sandbox payment marks the order paid, sends the email and the download works. ⬜ Runs on the prod host with the store's Asaas environment left at `sandbox` (the default) before switching to `production`.
- **M5: prod promote** — ✅ authorized 2026-10-02 by the owner in-session ("I authorize store to be published to production."; consent record `deploy/consent/store.prod.yml`). The ✅ marks the authorization; the cutover items below stay open until reached.
  - ✅ Dev validation (M3) complete.
  - ✅ `store.noctusai.com` serving the landing (2026-10-02, prod `c728f42a1`): container healthy, edge 200 on `/`, `/obrigado`, `/login`, `/api/health`; checkout 503 until an Asaas key is saved (by design), admin + webhook 401 unauthenticated; core CORS accepts the store origin (URL roster applied); DNS CNAME `store` → the prod tunnel, proxied.
  - ⬜ Asaas keys saved in `/admin` → Integrações; sandbox E2E (M4), then switch to production.

## Anti-goals

- ❌ Visible login button on public pages (owner decision).
- ❌ Store-local Asaas client — the charge goes through the seed organ.
- ❌ Public storage buckets — kit and author photo are served through the backend.
