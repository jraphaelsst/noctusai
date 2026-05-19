# Absorbed-product seed-shape-seam

> The recurring methodology pattern surfaced during the `social-wiring-google-seed-consume` project (2026-05-19). N≥3 in one project alone (token_store metadata, oauth_router prefix/callback_path, GoogleProvider PKCE) ⇒ MUST formalize. Single canonical doc — every other reference points here; never duplicate the body.

---

## 1. What the pattern is

When **absorbing** a product whose **pre-existing concrete shape** (a database table's columns, a registered external URL, an OAuth flow's added security control, a protocol field, …) **does not match the seed primitive's current default contract**, the seed-first resolution is:

> **Extend the seed primitive with a back-compat-defaulted shape-config parameter. Do NOT degrade the consumer. Do NOT fork in the product. Do NOT silently schema-migrate the consumer to fit the seed.**

The seed's defaults reproduce today's exact behavior (additive ⇒ zero existing-consumer impact, pilot-gate is provably a no-op for current consumers). The absorbed product opts in via the new parameter and consumes the seed seam directly.

This is the *granular* sibling of `KB § GUIDES/absorb-seed-workspace.md` — that guide is the 10-gate end-to-end procedure for absorbing a workspace into noc; **this pattern fires inside an absorption when a specific shape mismatch is discovered**.

---

## 2. The trigger (when this pattern fires)

The pattern fires when an architect/engineer audit hits any of:

- An absorbed product's **migration DDL** has columns/names/types the seed Real adapter's `put`/write payload doesn't produce (or doesn't read).
- An absorbed product holds a **registered-with-an-external-system identifier** (Google Cloud Console OAuth redirect URI, Stripe webhook endpoint, Meta App OAuth callback, …) at a path/shape the seed's generic primitive hardcodes differently — relocating it breaks production consents/endpoints.
- An absorbed product's flow uses a **security control or protocol feature** (PKCE, signed-state, custom auth header, idempotency key, …) the seed primitive doesn't currently implement.
- An absorbed product's data model uses **denormalized fields** the seed `StoredCredential`/Protocol DTO doesn't carry, but the seed store's `select("*")` happens to read past them.

**Litmus:** if "to consume the seed, we'd have to (a) change the consumer's external contract, (b) silently weaken a security control, (c) drop denormalized columns, or (d) reshape an existing DB row" → this pattern fires.

---

## 3. The canonical resolution shape

The seed primitive (Protocol+Fake+Real+factory) gains **one or more** of:

- **`<config_name>: T | None = <today's_default>`** — explicit shape-config parameter on `__init__` (or the `make_*` factory). Default `= <today's_default>` reproduces today's exact behavior.
- **Mapping parameter** — `<config_name>: dict[str, X] | None = None`. Lets the consumer wire its concrete shape (columns ↔ DTO fields, providers ↔ paths, scopes ↔ verifiers, …). `None` = "use the canonical default."
- **Per-call opt-in flag** — `use_<feature>: bool = False`. Off by default (preserves today); on opts the consumer into a stronger or specialized mode.

Whatever the shape, all four of these MUST hold (otherwise the pattern is implemented wrong):

1. **Defaults reproduce today's exact behavior.** Test it: a consumer that ignores the new parameters sees zero observable change.
2. **`Protocol` / public API surface is preserved** unless the addition is purely additive (an extra optional kwarg). New top-level identifiers go through `__all__`.
3. **Fake mirrors the Real adapter's new shape.** A consumer's test using the Fake exercises the same mapping the Real does.
4. **Pilot-gate verified, not assumed.** `pytest` of every pilot consumer (`erp-imobiliario`, `therapy-platform`, `social-wiring`, `core`) stays green BEFORE consuming. Additive-with-defaults ⇒ provably no-op, but verify.

Once the seam ships, the absorbed product **consumes it directly** (no product-local wrapper unless DRY-recurrence justifies a thin named seam — e.g. centralizing a loud config-guard at N consumer sites; that's still consumption, not a fork).

---

## 4. The three instances confirming the pattern (worked examples)

Each row links to the seed primitive + the seam parameter + the absorbed-product instance.

| Seed primitive | Seam parameter(s) | Why it was needed | Pilot-gate result |
|---|---|---|---|
| `noctusai_lib.security.token_store.SupabaseCredentialStore` | `metadata_column: str \| None = "metadata"` + `metadata_columns: dict[str,str] \| None = None` | `social_wiring.credentials` has no `metadata jsonb` column; carries denormalized `channel_id/channel_title/scopes`. Real `put()` would 100% fail PostgREST PGRST204; mock false-green. | Zero existing consumers; additive-with-defaults verified no-op. |
| `noctusai_lib.security.oauth.oauth_router` | `prefix: str = "/api/oauth"` + per-provider `callback_paths` override | social-wiring's `/api/youtube/oauth/callback` + `/api/calendar/oauth/callback` are registered in Google Cloud Console; relocating orphans every existing user consent. | Zero existing consumers; provably no-op. |
| `noctusai_lib.security.oauth.GoogleProvider` | `use_pkce: bool = False` (or equivalent) — PKCE `code_challenge`/`code_verifier` round-trip | social-wiring's YouTube flow had PKCE (via `google_auth_oauthlib` default). The seed `GoogleProvider` is confidential-client-only; migrating without this seam *drops* PKCE — a real security-posture reduction. Defense-in-depth for confidential clients per OAuth 2.1 / Google guidance. | Additive-with-defaults; pilot-gate no-op. |

**Recurrence threshold reached.** Per the DRY recurrence rule (`KB § PATTERNS/project-execution.md § 2.7`), N≥3 ⇒ MUST formalize. This doc IS the formalization.

---

## 5. Anti-patterns (forbidden resolutions)

- **Degrading the consumer to fit the seed gap.** Dropping PKCE because the seed doesn't have it; dropping a denormalized column because `StoredCredential` doesn't carry it. Silent security/behavior reduction. Anti-pattern.
- **Forking in the product.** Re-implementing the missing seed feature in a product-local module. This is the exact thing this project (and the seed-first rule) exists to eliminate.
- **Silent schema migration on the consumer.** Renaming columns / adding `metadata jsonb` / restructuring registered URLs to fit the seed. Affects production data + external systems — never silent, requires explicit user decision; almost always the wrong resolution.
- **Inline 27 `make_credential_store(...)` calls instead of a thin product consume-seam.** The thin seam (zero crypto/DB, delegates to seed) is *consumption*, not a fork (see `social-wiring/app/services/credential_vault.py` for the canonical shape). The seam centralizes config-guard recurrence; it's DRY-correct.

---

## 6. Trigger phrases for future agents

If you see / are saying any of these while doing absorption work, the pattern fires; STOP and route here:

- *"the seed doesn't ship a `<X>` parameter — let me drop/work-around it"*
- *"the absorbed product's table has extra columns the seed doesn't know about — let me ignore them"*
- *"the registered redirect URI is at `/api/<x>/...` but the seed router uses `/api/oauth/...` — let me update the Google Cloud Console"*
- *"the absorbed product had PKCE/HMAC/idempotency but the seed primitive doesn't — let me drop it for now"*

The correct routing in all four: extend the seed seam, back-compat-defaulted, pilot-gated. This doc.

---

## 7. Codification status

- **Stage 3 (s3):** this doc + `CLAUDE.md` pointer + `MEMORY.md` entry. Three-way synced 2026-05-19.
- **Stage 4 (s4) candidate:** a deterministic keeper that flags a seed-primitive Real-adapter's write-payload key set ⊄ the consumer's migration DDL columns (the false-green class). Routed to `phase_learnings`; not built yet (see `KB § PATTERNS/methodology-codification-pipeline.md`).

---

## 8. Pointers (don't duplicate the body here)

- 10-gate absorption procedure (the GUIDE this pattern lives inside) → `KB § GUIDES/absorb-seed-workspace.md`
- DRY recurrence rule (why N≥3 ⇒ MUST formalize) → `KB § PATTERNS/project-execution.md § 2.7`
- Seed Fake+Real factory shape (the seam expectations) → `KB § PATTERNS/seed-fake-real-adapter.md`
- The originating project (worked instances) → `products/social-wiring/projects/social-wiring-google-seed-consume/`
- Doc-vs-code sync rule → `KB § 01-PHILOSOPHY.md § Docs stay in sync`
