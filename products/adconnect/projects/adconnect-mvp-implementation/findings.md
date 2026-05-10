# findings.md — adconnect-mvp-implementation

> Per `feedback_knowledge_tracking.md`. Five categories. Append in-the-moment for surprises.
> Engineer A — Phase 0 audit + Phase 1 identity foundation. 2026-05-10.

---

## errors

_(none — Phase 0 audit ran clean.)_

## mistakes-slips

- **Brief vs reality on `auth_deps.py` removal.** PROJECT.md §6 Phase 1 says "REMOVE `app/auth_deps.py`". Direct removal would break 7 downstream routers (admin / orders / financial / rewards / sellout / distributors + auth itself) which are still mock-backed and will only be replaced in Phases 2-6. Resolution: REWROTE `auth_deps.py` as a thin delegation shim that re-exports `get_current_user` + `require_role` backed by the seed's `make_get_current_user` / `make_require_role` factories — same exported surface, no custom JWT decoding. Removal is deferred to Phase 6 once the last mock router is swapped. PROJECT.md §6 Phase 1 updated to reflect this. `app/security.py` IS removed (no longer needed under Option A).

## lessons

- **Verify-the-seed-ships-it (the SHAPE, not just the parts).** PROJECT.md §5.5 listed "SSO" as inherited from `seed/lib/backend/noctusai_lib/security/oauth/`. That path doesn't exist — SSO primitives live in `noctusai_lib/api/auth.py` (`make_get_current_user`, `make_get_current_user_org`, `make_require_role`, `resolve_sso_role`, `create_sso_token_factory`, `verify_sso_token_factory`, `SSOSessionCache`). Per the rule, I read `seed/lib/backend/noctusai_lib/api/auth.py` directly before locking the consumption decision. Real adapter shipped: confirmed (`make_get_current_user` is the production wrapper used by ERP / PF / Therapy / Core).
- **Brief asks for `noctus.seed.audit_drift` + `noctus.seed.list_capabilities` + `noctus.seed.scan_repetition`.** Those names don't exist in the MCP server. Closest analogues: `noctus.dev.diff_against_seed` (ran — see knowledge-pieces), `noctus.dev.validate` (output exceeded MCP token limit; skipped — see open-questions), `noctus.dev.scan_within_product_helpers` (ran — adconnect has zero in-product duplications, expected since it's mostly mock scaffolding). Methodology learning logged as a candidate for three-way sync: align PROJECT.md drafts with actual MCP tool names by running `claude mcp list` first.
- **ERP and Therapy use opposite identity shapes.** ERP uses `auth.users` directly + an `erp.profiles` shim; tenanting via `noctus_users.org_id` from core (no sub-entity layer because every ERP user belongs to one company-org-1-1). Therapy uses a sub-entity table (`therapy.clinics`) + per-row `clinic_id` FK; the `current_clinic_id()` helper reads it from JWT user_metadata. **AdConnect's distributor sub-entity shape mirrors Therapy's clinics, not ERP's profiles** — distributors are sub-entities under the brand org, multiple users per distributor, just like clinics.
- **No `noctusai_lib.domain.subentities` exists.** PROJECT.md §5.1 hypothesized one; absent. The recurrence right now is N=2 (therapy.clinics + adconnect.distributors-once-shipped) — triage outcome: **accept-with-rationale** for now (each sub-entity has product-specific columns; the only shared shape is "sub-entity_id FK + membership table"). Recurrence flips to **formalize** if PF or ERP later grow a similar layer (companies-within-org, agencies-within-brokerage, etc.). Add to `KB § PATTERNS/accept-with-rationale.md` post-merge.

## interesting-findings

- **The seed framework's `team` standard router already handles invitations** — `products/core/backend/app/routers/team.py` is mounted at `/api/team/invite` for every product via `standard_routers=["team"]`. AdConnect main.py:51 already includes "team". Phase 1's invitation flow can EXTEND this surface for distributor-targeted invitations (the existing flow targets `noc.noctus_users` org membership; we layer a `distributor_id` parameter that triggers a `distributor_memberships` insert on acceptance). Implementation lands a thin `/api/auth/accept-distributor-invite` endpoint that consumes the seed-level invitation token and creates the membership row.
- **AdConnect's `app/data/store.py` has `users` and `orders` as in-memory dynamic lists** — every other JSON-backed list is loaded once from disk and read-only. The `users` field IS the in-memory auth backing scheduled for removal in Phase 1. The `orders` field stays for Phase 3 (still mock-backed at that point); will be removed when the orders router is swapped.
- **`noctusai_lib.api.auth.make_get_current_user_org` was added 2026-05-04** to formalize the (user, token, org_id) tuple shape — auto-handles missing org_id with HTTPException. Phase 1's `dependencies.py` for AdConnect should use this directly rather than the deprecated `ProductDependencies.get_org_id`.
- **AdConnect's `dependencies.py` currently uses the deprecated `ProductDependencies` shape** (`get_org_id` as a Depends() target). The deprecation warning at `noctusai_seed/dependencies.py:46-53` documents that this returns 422 — but currently no router consumes it as Depends, so it's dormant. Future phases should switch any new domain dep to `make_get_current_user_org`.

## knowledge-pieces

### Seed inventory (`noctusai_lib` + `noctusai_seed` exports)

`noctusai_seed` (framework — `seed/framework/backend/noctusai_seed/`):
- `create_product_app(name, schema, settings, routers, version, limiter, standard_routers=[...])` — the inheritance entry point. Every product wires through this.
- `create_database_module(settings, schema)` — Supabase client factory.
- `create_dependencies(db)` → `ProductDependencies` (deprecated as `Depends()` target — use `noctusai_lib.api.auth.make_get_current_user_org` instead).
- `health.py` — standard `/api/health` router.
- `routers.py` — standard router registry (health / team / notificacoes).

`noctusai_lib` (lib — `seed/lib/backend/noctusai_lib/`):
- `api/auth.py` — `make_get_current_user(get_supabase_client_fn)`, `make_get_current_user_org(...)`, `make_require_role(...)`, `resolve_sso_role(user)`, `get_sso_context(user)`, `first_or_none(result)`, `create_sso_token_factory(settings)`, `verify_sso_token_factory(settings)`, `SSOSessionCache`.
- `api/app_factory.py`, `api/middleware.py`, `api/rate_limit.py`, `api/scheduler.py`, `api/product_urls.py`.
- `domain/sql_templates.py` — `set_search_path()`, `updated_at_function()`, `updated_at_trigger()`, `rls_subquery_policy()`. Authoring-time helpers for canonical migration shape.
- `domain/scheduling/`, `domain/chatbot/`, `domain/digest/`, `domain/ai/`, `domain/metas/`, `domain/jobs/`.
- `integrations/email/digest.py` — `send_to_one`, `send_to_many`, `send_digest`. Resend + SMTP backends with org-scoped config resolution.
- `integrations/database.py`, `integrations/redis.py`, `integrations/storage/`, `integrations/llm/`, `integrations/quota/`, `integrations/google_calendar/`, `integrations/google_drive/`, `integrations/google_maps/`, `integrations/whatsapp/`, `integrations/youtube/`, `integrations/vista/`, `integrations/supabase_identity.py`.
- `security/` — webhook signatures + crypto.
- `testing/` — `MockSupabaseClient`, `MockUser`, `AuthClient`, `bind_consent_module_to_mock`, `MockRequestBuilder`.
- `primitives/`, `config/`, `logging_config.py`.

### Drift report (`noctus_dev_diff_against_seed` against `adconnect`)

```
frontend/vite.config.ts: 3c3
< export default createViteConfig({ port: 8100 });
---
> export default createViteConfig({ port: 8130 });
frontend/tailwind.config.ts: identical
frontend/tsconfig.json: identical
```

**Verdict:** the only structural drift is the port (8100 vs the seed default 8130) — that's expected and correct (port allocation is per-product). Backend has no compared shape because the seed only ships frontend templates for diff. Backend is structurally aligned (`main.py` uses `create_product_app`).

### ERP/Therapy hierarchy pattern (canonical sub-entity shape)

**ERP** (`products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql`):
- No sub-entity layer. Each user has one `auth.users` row, one `erp.profiles` row (1:1).
- Tenanting: `noctus_users.org_id` from core. Every domain row has `usuario_id UUID REFERENCES erp.profiles(id)` or `owner_id UUID REFERENCES auth.users(id)`.
- RLS: `(SELECT auth.uid()) = usuario_id` (subquery shape per `KB § PATTERNS/database-rls.md`).
- Membership = single user → single org. **Doesn't apply to AdConnect's brand→distributor→user.**

**Therapy** (`products/therapy-platform/backend/migrations/001_therapy_platform.sql`):
- Sub-entity layer: `therapy.clinics` (id, name, cnpj, …). Used as a "company within the platform org".
- Membership rows: `therapy.therapist_profiles.clinic_id` FK (one-to-many: one clinic, many therapists).
- Helper functions in SQL: `therapy.current_user_role()` reads role from JWT user_metadata; `therapy.current_clinic_id()` reads clinic_id from JWT user_metadata (NOT a join table).
- RLS: `(SELECT therapy.current_clinic_id()) = clinic_id` shape — relies on JWT-injected metadata.
- **This IS the canonical sub-entity pattern AdConnect's distributor layer mirrors.**

**Core** (`products/core/backend/migrations/001_noctusai_core.sql`):
- `organizations` (tenants), `noctus_users` (id matches auth.users.id, FK to organizations).
- `org_role` column: `owner | admin | member | viewer`.
- `role` column (legacy): `admin | manager | user`.
- RLS pattern: `id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid()))`.

### Canonical RLS pattern for "user belongs to N entities, sees only their entity's data"

Therapy's pattern (the closest analogue to AdConnect's):
1. **Membership stored** in a per-row FK on the data table (e.g. `appointments.clinic_id`) AND/OR a JWT-injected metadata field (`therapy.current_clinic_id()`).
2. **Policy** uses subquery shape `(SELECT auth.uid())` for performance, and either:
   - Direct equality on a JWT helper: `clinic_id = (SELECT therapy.current_clinic_id())`, OR
   - Subquery against a membership table: `clinic_id IN (SELECT clinic_id FROM ... WHERE user_id = (SELECT auth.uid()))`.

For AdConnect — distributor users may belong to MULTIPLE distributors (PROJECT.md §7 #6: "can the same person belong to two distributors? schema says yes"). Therefore the **subquery-against-membership-table** shape is mandatory; JWT-helper shape only works for 1:1 user→clinic. AdConnect uses:

```sql
distributor_id IN (
    SELECT distributor_id FROM adconnect.distributor_memberships
    WHERE user_id = (SELECT auth.uid())
)
```

For brand-side admin (sees all distributors in their brand org):

```sql
EXISTS (
    SELECT 1 FROM noctus_users u
    JOIN adconnect.distributors d ON d.org_id = u.org_id
    WHERE u.id = (SELECT auth.uid())
      AND u.org_role IN ('owner', 'admin')
      AND d.id = adconnect.<table>.distributor_id
)
```

This is what migration `002_adconnect_identity.sql` ships.

### Mock JSON audit (production schema decisions)

Every mock JSON read; for each: production schema mirrors / diverges + why.

| Mock file | Production schema decision | Reason |
|---|---|---|
| `distributors.json` | **DIVERGE** — drop `smartTier`, `smartActive`, `annualRevenue`, `annualGoal`, `totalOrders`, `cashbackBalance`, `mktBalance`, `lastOrder`, `selloutCompliance`, `paymentScore`, `trend` (these are computed metrics, not entity state). Drop nested `cnpjs[]` array — promote to a separate `adconnect.distributor_cnpjs` table for normalization (a distributor can have N tax-IDs per the mock). Keep: `id, org_id, cnpj (primary), nome, contato_nome, contato_email, contato_telefone, endereco_cidade, endereco_uf, status, created_at`. | Computed metrics belong in materialized views or service-layer aggregation, not on the entity row. CNPJs array is a 1:N relationship that belongs in its own table. |
| `products.json` | **DIVERGE** — keep `id, nome, sku, categoria_id FK, preco_base, em_estoque, marca`. Drop `priceB2B` field — that's actually a per-distributor-tier preferential-pricing concept; goes into `adconnect.precos_distribuidor` (Phase 2) keyed off distributor + product. Drop `cashback` from the `products` table; `cashback` is per-rule (rewards engine, Phase 4). Keep `min_pedido`, `multiplo` columns on the product row — promote to per-distributor override only on N=2. | The mock conflated catalog data with rewards rules and pricing tiers. Production separates them. |
| `categories.json` | **MIRROR mostly** — `id (→ uuid), nome`. The mock uses string IDs (`"cat6"`); production uses UUID + a `slug` column for URL-friendliness. | UUID for FK consistency; slug preserves the human-readable identifier. |
| `promos.json` | **DIVERGE** — combines product-level info (sku, product name) with promo state. Production normalizes: `adconnect.promos (id, sku|product_id FK, type, label, cashback_pct, mkt_budget_pct, valid_from, valid_to, active, created_at)`. Drop the `product` (name) field — join to `products`. Drop the special `"exception"` type that has no actual effect — replace with an `is_excluded` boolean column. | Mock embeds redundant product info. |
| `reward-rules.json` | **DIVERGE significantly** — the mock has `tiers: { SMARTER, MASTER, INSIDER, STARTER }` keyed by string. Production splits into: `adconnect.regras_recompensa (id, sku|product_id FK, category_id FK, min_qty, active, created_at)` + `adconnect.regras_recompensa_tiers (id, regra_id FK, tier TEXT, cashback_pct DECIMAL, mkt_budget_pct DECIMAL)`. Lock the `tier` enum at migration time: `STARTER | INSIDER | MASTER | SMARTER`. Add `tier` to `adconnect.distributors` (or to `adconnect.distributor_memberships` if a user-level tier is ever needed) so the rewards engine can join. | Tiers as JSON object are not queryable. |
| `rewards-history.json` | **DIVERGE** — every row has `orderId`, `type` (`cashback | verba_mkt`), `status` (`Pendente | Liberado | Utilizado`), `description`, `amount`. Production: `adconnect.recompensas_acumuladas (id, distributor_id FK, source_pedido_id FK NULL, source_relatorio_sellout_id FK NULL, tipo TEXT CHECK IN ('cashback', 'verba_mkt'), valor NUMERIC(12,2), status TEXT CHECK IN ('pendente', 'liberado', 'utilizado', 'expirado'), description, created_at)`. Add `expirado` status (mock missing) and `created_at`. Portuguese-snake-case status enum. | Mock has English status; production uses Portuguese. |
| `sellout-reports.json` | **DIVERGE** — mock has single Excel-attachment shape. PROJECT.md §2 mandates THREE submission modes. Production: `adconnect.relatorios_sellout (id, distributor_id FK, periodo_inicio DATE, periodo_fim DATE, modo TEXT CHECK IN ('estruturado', 'nfe_xml', 'anexo_livre'), status TEXT CHECK IN ('pendente', 'aprovado', 'recusado'), motivo_recusa TEXT NULL, total_itens INT, total_unidades INT, total_valor NUMERIC(12,2), nfe_xml BYTEA NULL, anexo_url TEXT NULL, dados_estruturados JSONB NULL, submitted_at TIMESTAMPTZ, reviewed_by UUID NULL, reviewed_at TIMESTAMPTZ NULL, created_at)`. | Mock predated the three-mode requirement. |
| `invoices.json` | **DIVERGE** — mock has `nfe (number), orderId, issueDate, dueDate, amount, status (em_aberto, pago, vencido)`. Production: `adconnect.faturas (id, distributor_id FK, pedido_id FK, nfe_numero TEXT, nfe_xml BYTEA, stripe_invoice_id TEXT, valor NUMERIC(12,2), data_emissao TIMESTAMPTZ, data_vencimento TIMESTAMPTZ, status TEXT CHECK IN ('em_aberto', 'pago', 'vencido', 'cancelado'), created_at)`. Add `nfe_xml` BYTEA + `stripe_invoice_id` (Phase 5). Add `cancelado` status (mock missing — needed for refund flow). | Phase 5's NF-e + Stripe inheritance both demand additional columns. |
| `users` (in-memory `store.users`) | **DROP entirely** — Option A locks identity in `noc.noctus_users` + `adconnect.distributor_memberships`. The in-memory list is the password-hashing JWT scaffold this project removes. | Custom JWT auth retired under Option A. |

### Auth model lock-in — Option A (distributor-as-noc-user)

**Locked decision:** distributor users live in `noc.noctus_users` with `org_id` = brand's org id. Distributor membership lives in `adconnect.distributor_memberships (user_id, distributor_id, role)`. SSO uses the platform's standard surface (Supabase auth + `noctusai_seed`'s `team` standard router for invitations). Custom JWT in `app/security.py` is removed. `app/auth_deps.py` is rewritten as a thin delegation shim re-exporting `get_current_user` + `require_role` from the seed lib factories (NOT removed outright — see mistakes-slips above).

**Migration path to Option B (distributor-as-external-org), if ever needed:**
1. Author migration `00X_promote_distributors_to_orgs.sql` that for each row in `adconnect.distributors`, creates a matching `noc.organizations` row with `slug = 'distributor-' || cnpj-stripped`.
2. For each `adconnect.distributor_memberships` row, update the corresponding `noc.noctus_users.org_id` to point at the new distributor-org instead of the brand-org.
3. Add a `noc.cross_org_grants (granter_org_id, grantee_org_id, scope)` table and grant brand→all-distributors read access.
4. Update RLS policies on every `adconnect.*` table to use `noc.cross_org_grants` joins instead of `adconnect.distributor_memberships`.
5. Cost: ~2-3 days across 7 tables + every router that uses the membership shape. Defer until 2nd brand customer asks for it.

### Stripe entry point (Phase 5 inherits this — verified)

`products/core/backend/app/services/stripe_service.py`:
- `create_customer(org_id, email, name)` → Stripe Customer ID.
- `create_checkout_session(price_id, customer_id, success_url, cancel_url, metadata)` → Stripe Checkout URL.
- `create_portal_session(customer_id, return_url)` → Customer Portal URL.
- `cancel_subscription(subscription_id)`.
- `get_invoices(customer_id)`.
- `construct_webhook_event(payload, sig_header)` → verified Stripe webhook event.

`products/core/backend/app/routers/billing.py` mounts these on `/api/billing/*`. AdConnect's Phase 5 `financial_service.py` consumes `stripe_service` directly via cross-product import (`from products.core.backend.app.services.stripe_service import ...`) — webhooks already routed by core.

**Verify-the-seed-ships-it test:** Real adapter SHIPPED (`stripe_service.py` is the production wrapper, not a Fake). `_ensure_api_key()` reads `STRIPE_API_KEY` from env at module load.

### Email entry point (Phase 3+ inherits this — verified)

`seed/lib/backend/noctusai_lib/integrations/email/digest.py`:
- `send_to_one(*, to: str, subject: str, html: str, text: str = "", org_id: Optional[str] = None) → DigestSendResult` (async).
- `send_to_many(*, to: list[str], ...) → list[DigestSendResult]`.
- `send_digest(*, digest: Digest, ...)`.
- Backend selection: per-org Resend config → fallback per-org SMTP config → fallback platform-default. Resolved via `_resolve_email_backend(org_id)`.

**Verify-the-seed-ships-it test:** Real adapter SHIPPED — `_post_to_resend()` is the production HTTP call against Resend's REST API, not a Fake.

### LGPD flag types applicable to distributor data

From `noctus.dev.lgpd_list` — current entries are unrelated (Vista CRM, therapy patient data, longitudinal aggregation, LLM-cache cross-org). No existing AdConnect entries.

**New flags Phase 1+ creates:**
1. **CNPJ + business address** at distributor registration (`adconnect.distributors`) — concern: PII (Brazilian tax IDs are personal data when the entity is a sole proprietor / MEI; addresses are PII). Reason: "Distributor PII at registration; retention TBD by product owner".
2. **Contact name + email + phone** — same flag site. Concern: PII. Reason: "Distributor contact PII".
3. **Payment data** at invoice issuance (`adconnect.faturas`) — Phase 5. Concern: financial PII.
4. **NF-e XML upload** at sellout (`adconnect.relatorios_sellout`) — Phase 4. Concern: contains CNPJ + line items + totals.

Flag tool signature: `noctus.dev.lgpd_flag(code_path: str, concern: str, reason: str, mitigation: Optional[str] = None)`. **Note:** the tool does NOT accept `table=` / `fields=` arguments (PROJECT.md §6 Phase 1 step 7 used a hypothetical signature). The real signature wraps file paths + free-text concern. Phase 1 implementation flags via `code_path="products/adconnect/backend/app/routers/auth.py"` + concern strings naming the specific fields. Concretely flagged: see `LGPD-WARNINGS.md` post-merge.

### Verify-the-seed-ships-it summary

| Capability | Real adapter ships? | Verdict |
|---|---|---|
| `create_product_app()` | YES — already used in main.py | OK |
| Stripe (`stripe_service.py`) | YES — `_ensure_api_key()` + production stripe SDK | OK |
| Email (`digest.send_to_one`) | YES — `_post_to_resend()` | OK |
| Webhook signatures | YES — `noctusai_lib/security/webhook_signatures.py` | OK |
| SSO (`make_get_current_user`) | YES — Core consumer; production wrapper used by ERP/PF/Therapy | OK |
| LGPD flag tooling | YES — MCP tool `noctus.dev.lgpd_flag` | OK (signature differs from PROJECT.md draft — see above) |
| Storage bucket | UNVERIFIED — defer to Phase 4 | DEFER |
| NF-e parsing helper | NO — file-not-found in `noctusai_lib`; Phase 4 ships local | local for now |

**Conclusion:** all Phase 1 / Phase 5 consumption decisions are runtime-ready. Phase 4 has two items to re-verify when that phase opens.

---

## Engineer B — Phase 7 frontend skeleton (2026-05-10)

### errors

- **Subagent .md writes blocked despite explicit dispatch authorization.** Engineer B's brief carried a Write-authorization paragraph for `findings.md`. The Write tool refused with *"Subagents should return findings as text, not write report files."* Workaround: orchestrator captured findings on engineer's behalf (this section). Methodology gap — runtime-injected "never create *.md files" subagent default wins over the dispatch brief's override. If recurrence fires once more, formalize "orchestrator captures findings" pattern in `KB § PATTERNS/branching-and-merging.md § 17.6`.
- **Seed factory baseline build broken in worktree from `main`.** `seed/framework/frontend/vite.config.factory.ts` had two pre-existing gaps: `FRAMEWORK_DEPS` array missed `clsx` + `tailwind-merge` (peer-deps of `seed/lib/frontend/`); `PRODUCT_MAP` missed `adconnect` (port 8130 → backend 8007 → schema `adconnect`). Same fix exists on parallel branch as commit `f1a3935`. Engineer B re-applied minimally inside their worktree to unblock build; collision-protocol decision deferred to merge.

### lessons

- **`PRODUCT_MAP` is a recurring conflict locus.** Single-source-of-truth registry that needs updating per-scaffold. Same conflict shape as MCP-tool-registration alphabetical-ordering. Worth formalizing as one row per file (`seed/framework/frontend/products/<slug>.config.ts`) with a registry-loader pattern — eliminates the central-file collision entirely. **Recurrence rule:** N=2 = triage time. Decision deferred to retrospective; if a third scaffold-collision lands, formalize.

### interesting-findings

- **Phase 7 PROPER swap is one-file-per-hook.** Hook bodies follow React Query `{data, isLoading, error}` shape verbatim with `// TODO(adconnect-phase-7)` comments naming the endpoint each will consume. Pages already destructure the React Query shape — Phase 7 PROPER (real API integration) is mechanical, no consumer changes.
- **Status enums keep PT verbatim.** `OrderStatus`, `SelloutStatus`, `RewardStatus` use the planned schema's PT values (`rascunho`, `pendente`, `aprovado`, `enviado`, `confirmado`, `entregue`, `cancelado`, …) so the frontend type matches the DB string with zero translation surface. Naming convention: PT for UI strings + DB enum values; EN for routes/types/code identifiers — per PROJECT.md §2.
- **Frontend deps already in place.** `react-hook-form ^7.61.1`, `@tanstack/react-query ^5.83.0`, `@hookform/resolvers ^3.10.0` all in `products/adconnect/frontend/package.json`. Phase 7 PROPER needs zero `npm install` round-trips.

### knowledge-pieces

**Frontend skeleton inventory** — pages at `products/adconnect/frontend/src/pages/` (Catalog / ProductDetail / Cart / Checkout / Orders / OrderDetail / SelloutReportSubmit / SelloutHistory / RewardsLedger) + hooks at `src/hooks/` (useCatalog+useProduct / useCart+useCartMutations / useOrders+useOrder+usePlaceOrder / useSellout+useSubmitSellout / useRewards+useRedeemRewards) + types at `src/types/index.ts` (Distributor / Product / Cart / Order / SelloutReport / Reward + status enums) + 10 routes wired into `App.tsx` (`/catalog/:id`, `/orders/:id` included) + 2 nav groups (Marketplace + Recompensas e sellout).

`vite build` result: ✓ built in 9.17s — clean. All pages compiled into individual lazy chunks (1-7 kB each).

---
