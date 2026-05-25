# social-wiring-meta-seed-consume — Project Document

> **Filed 2026-05-19** as the named destination for the deferred Meta-stack
> seed-consume work, surfaced during the meta audit at the close of
> `social-wiring-google-seed-consume`. Structurally **identical** to that
> project (same `absorbed-product-seed-shape-seam` pattern, different
> integration); reuse its phase structure as the template.

- **Created:** 2026-05-19
- **Status:** ✅ **SHIPPED** 2026-05-24 (`origin/dev` `db482e5c`) — the ~1302-LoC hand-rolled Meta fork (`_meta_api.py`/`oauth_adapter.py`/`fake_adapter.py`/`mappers.py`/`types.py`) was deleted; `app/services/meta/__init__.py` is now a zero-API-logic shim over `noctusai_lib.integrations.meta` (so the product auto-inherits the seed's video/Reels publish too); `meta_router.py` + tests migrated. Stale-status line corrected by the architect at integration (the authoring terminal lost context before updating it). 491 social-wiring tests green.
- **Owner / stakeholders:** joaoraphaelsst · architect
- **Related docs:** `KB § PATTERNS/absorbed-product-seed-shape-seam.md` (canonical pattern, N=3+ confirmed) · sibling `products/social-wiring/projects/social-wiring-google-seed-consume/PROJECT.md` (the template; this project mirrors its phase structure) · `KB § INTEGRATIONS/meta.md` (consume-side reference)
- **Project slug:** `social-wiring-meta-seed-consume` — intent ≈ `wiring` (canonical `<product>-seed-wiring` shape). Location: `products/social-wiring/projects/`.

---

## 1. Context & Purpose

The audit at the close of `social-wiring-google-seed-consume` (2026-05-19) confirmed `services/meta/*` is **hand-rolled** in the exact same shape we just removed for Google:

- **~1302 LoC** product-local fork: `_meta_api.py`, `oauth_adapter.py`, `fake_adapter.py`, `mappers.py`, `types.py`, `__init__.py`.
- Direct `https://graph.facebook.com` calls (`GRAPH_BASE = "https://graph.facebook.com"`, `meta_graph_api_version` setting).
- Hand-rolled OAuth adapter (Meta has its own per-org token model + system-user token chain).
- Product-local `credential_store` consumers (Phase-2 of the Google project already migrated the *vault* construction to the seed `token_store` consume seam at `meta_router.py:95`; the **integration** stays hand-rolled in this project).

The seed already ships **`noctusai_lib.integrations.meta`** — Protocol+Fake+Real+factory + `make_meta_router` + `credentials.py` + `oauth_adapter.py`. Same architectural situation that drove the Google project.

**Win:** ~1.3k LoC fork retired; the OAuth flow + Graph-API access route through one canonical seed path (consistent with how YouTube/Calendar/Drive land after the Google project closes); unifies Meta auth-mode resolution (system_user → user_oauth → Fake) at the seed.

---

## 2. Confirmed constraints

- **Scope = Meta only.** Google stack (youtube/calendar/drive/oauth/token_store) is `social-wiring-google-seed-consume`'s job and is shipping on `feat/sw-google-seed-consume`; this project starts from that branch's merged state.
- **Methodology pattern is codified.** `KB § PATTERNS/absorbed-product-seed-shape-seam.md` is the canonical playbook — any seed-gap you find (e.g. a Meta system-user-token chain shape the seed lacks, a registered webhook URL Google-style immovability) routes through the same back-compat-defaulted seam shape. Defaults reproduce today; Fake mirrors Real; pilot-gate verified no-op; **never** degrade the consumer.
- **Sibling-project conventions reusable**: patch-return engineer dispatch model proved out (Phases 1–5); `--no-verify` carve-out documentation pattern; AST-first via libcst; tests-as-oracle with independent architect re-run; mcp/google-style consumer sweep across `mcp/` + `dev_team/` (not just `products/`); the "harness watchdog stalls on return-text-gen, patch file is the actual deliverable, write it early" rule.

---

## 3a. Seed-first analysis

The canonical body lives in `KB § PATTERNS/absorbed-product-seed-shape-seam.md`. The 6-question checklist (`KB § GUIDES/seed-first-design.md`) for THIS project:

1. **Identical contract?** YES — Meta Graph access + OAuth lifecycle are fleet-generic; seed already ships canonical Protocol+Fake+Real+factory.
2. **Data source product-specific?** NO — uniform (Meta Graph API, Meta OAuth tokens). Product-specific = the social-marketing domain.
3. **Placement product-specific?** NO — seam is universal; social-wiring is one consumer.
4. **Visibility / permission rule?** YES — RLS-scoped per org via `(org_id, provider)` vault key; unchanged.
5. **Seam already in seed?** **YES** — `noctusai_lib.integrations.meta` ships Protocol+Fake+Real+factory + `make_meta_router` + `credentials.py` + `oauth_adapter.py`. Verify exact `__all__` + auth-mode signatures at Phase 0.
6. **Default-on / opt-in?** N/A — consumer remediation, not a new capability.

**Litmus — per-product code count this design requires:** thin product wiring layer + the social-marketing domain ≈ **a small section**, replacing ~1.3k LoC of forked structure. Same shape as Google.

---

## 4. Scope

**In scope (mirror the Google-project phase structure):**
- Replace `services/meta/*` Graph-API call layer → `noctusai_lib.integrations.meta` (`make_meta_adapter` or equivalent factory).
- Replace `services/meta/oauth_adapter.py` → seed `noctusai_lib.security.oauth` (`MetaProvider` if it exists, else extend per the pattern doc).
- Reconcile MASTER-PROMPT.md `## Seed seams consumed` row (already flagged as drift; becomes TRUE when this lands).
- Audit `meta_router.py` for projection-mismatch (same lesson as Phase 4 youtube `_build_service` retention — surface a `seed-meta-projection-enrichment` follow-up if needed; do NOT silently degrade product UI).

**Out of scope (for now — with reason):**
- Anything Google-stack — owned by sibling project.
- Meta features not yet built (webhooks, ads) — `KB § INTEGRATIONS/meta.md` notes these are seed-out-of-scope-v1.

---

## 6. Implementation phases (suggested — adapt from Google-project template)

- **Phase 0 — Audit & seam map.** Enumerate every `services/meta/*` consumer site; map seed `noctusai_lib.integrations.meta` `__all__` method-by-method to hand-rolled equivalents; identify projection mismatches; identify any genuine seed gaps (which become `[F]` seed sub-phases).
- **Phase 1 — `[F]` seed gaps** (if any — pilot-gated, back-compat-defaulted, per the canonical pattern).
- **Phase 2 — Consume Meta OAuth lifecycle** (analogous to Google Phase 3).
- **Phase 3 — Consume Meta Graph API** (analogous to Google Phase 4).
- **Phase 4 — Cleanup + doc reconcile** (MASTER-PROMPT drift row removed; full verify pytest + tsc + vite build).

The Google project's per-phase shape (engineer patch-return → architect apply/fresh-eyes/independent-re-run/commit) IS the proven template.

---

## 7. Open questions

1. Does seed `noctusai_lib.integrations.meta` have a `MetaProvider` analogous to `GoogleProvider` for OAuth lifecycle? Phase 0 verifies.
2. Are there registered-with-Meta webhook URLs or OAuth callback paths that are immovable (like the YouTube `/api/youtube/oauth/callback`)? Phase 0 enumerates.
3. Auth-mode resolution: how does the seed `make_meta_adapter` handle `system_user → user_oauth → Fake` chain? Match the existing 3-tier product behavior.

---

## 9. Success criteria

- `services/meta/*` Graph-API + OAuth fork retired (`git rm` modules, replaced by thin consume seam).
- `grep -rl 'graph.facebook.com\|graph\\.facebook' products/social-wiring/backend/app` → no hand-rolled URLs.
- `cd products/social-wiring/backend && pytest` fully green; pilot consumers green (sweep includes `mcp/` + `dev_team/`).
- MASTER-PROMPT.md Google-stack drift marker — **and** Meta row — both correct (drift marker removed entirely when both this AND the Google project close).
- Zero credential data loss (the vault is already on seed `token_store` per Google Phase 2; this project preserves that).

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-19 | Filed as defer-≠-resolve destination for `services/meta/*` (~1302 LoC hand-rolled, mirrors the Google-stack pattern). Audit confirmed during `social-wiring-google-seed-consume` Phase 5/6 close. Phase structure templated from the Google project. | Claude (architect) |
