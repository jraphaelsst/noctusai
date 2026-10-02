# Roadmap — store launch (2026-10)

> Milestone bullets get ✅ only when genuinely reached. `M5` is the prod-promotion milestone referenced by `deploy/consent/store.prod.yml` (`KB § PATTERNS/devops/prod-exposure-consent.md`).

## Origin

On 2026-10-02 the owner asked to sell the generic "Contrato de Compra e Venda de Imóvel" (people ask Gilson for it on Instagram) as a digital product: a sales landing page in the Store Visual Identity, Asaas checkout, and a `/login` (no visible button) to edit the page's values. Owner decisions: `store.noctusai.com` first (own domain later), delivery by email + thank-you page, admin = only the owner, price R$ 47.

Contract: `products/store/projects/store-v1-CONTRACT.md`.

## Milestones

- **M1: scaffold** — seed-first scaffold, core catalog-row migration, contract. ✅ reached 2026-10-02 (`21a013b32`).
- **M2: seed one-off checkout** — `integrations.payments` one-off charge (Fake + Asaas + Stripe + factory), lifted from p-studio's product-local `criar_cobranca`. ⬜
- **M3: store BE + FE** — public landing, `/obrigado`, checkout, webhook fulfillment (email + signed download), `/admin` settings + sales; tests green; `predeploy_check` ready. ⬜
- **M4: Asaas sandbox end-to-end** — a sandbox payment marks the order paid, sends the email and the download works. ⬜
- **M5: prod promote** — `store.noctusai.com` serving the landing, `/login` admin restricted to the owner, real Asaas keys configured. ⬜

## Anti-goals

- ❌ Visible login button on public pages (owner decision).
- ❌ Store-local Asaas client — the charge goes through the seed organ.
- ❌ Public storage buckets — kit and author photo are served through the backend.
