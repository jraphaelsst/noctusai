# findings.md — erp-imobiliario-test-baseline-recovery

> Engineer G — REDISPATCH (after E surfaced env-drift blockers; architect refreshed env + pushed `origin/main = 26e40a11`).

---

## P0 — Real baseline confirmed

**Command:** `/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/pytest --tb=line -q` from `products/erp-imobiliario/backend/`

**Before:** `31 failed, 2044 passed, 34 skipped, 1 warning in 36.76s` — matches brief hypothesis exactly. The env-refresh did NOT change the failing-test count; the 986-TypeError-storm E observed in shared site-packages was orthogonal noise (env-tainted state), the 31 failures are the real baseline-red.

**After (P1-P4 inline drain):** `2075 passed, 34 skipped, 1 warning in 36.64s` — 0 failed. Stable across 2 consecutive runs.

### Cluster table (final, vs hypothesis)

| # | Cluster | File | Brief hypothesized | Actually failing | Root cause | Fix shape | Status |
|---|---|---|---|---|---|---|---|
| 1 | whatsapp_webhook | tests/routers/test_whatsapp_webhook_router.py | 8 | 10 (8 WAHA + 2 HMAC) | mock-skew: fixtures missing `waha_session_name`/`provider`/`is_active` so resolver returned no session row → router short-circuited `session_not_configured` | libcst AST transform: add 3 required fields to 16 `set_table_data("whatsapp_config", ...)` calls | ✅ |
| 2 | certidoes | tests/routers/test_certidoes_router.py | 8 | 8 | seed-internal: `noctusai_lib.config.credentials._get_public_client` constructs real Supabase client with empty url (`configure_credentials(url="")` at boot) when background task hits `resolve_credential`; test `client` fixture didn't patch this boundary | Patch `_get_public_client` in the conftest `client` fixture (precedent: `test_standard_llm_smoke.py`'s `llm_client` fixture; external-boundary mock per `KB § PATTERNS/testing.md`) | ✅ |
| 3 | configuracoes | tests/routers/test_configuracoes_router.py | 2 | 2 (`test_openai_sucesso` + `test_openai_erro_conexao` — `test_openai_chave_invalida` was already-fixed) | code drift: router was refactored 2026-05-11 (LLM-ERP Step A) to route via `noctusai_lib.integrations.llm.chat_completion`; tests still mocked `httpx.AsyncClient` (old `/v1/models` path) | Re-target the mock at `noctusai_lib.integrations.llm.chat_completion`; for the LLMAPIError branch use the correct `LLMAPIError(provider, message, status_code)` ctor | ✅ |
| 4 | emails (router) | tests/routers/test_emails_router.py | 1 | 0 (fixed by cluster 2's conftest patch) | same root cause as cluster 2 — email service called `resolve_credential` in test path | conftest patch ripple — no per-test edits needed | ✅ |
| 5 | gamificacao | tests/routers/test_gamificacao_router.py | 1 | 1 | mock-skew: fixture row lacked `user_id` so `.eq("user_id", user.id)` filter excluded it → badge appeared locked | Add `"user_id": "test-user-123"` to fixture (matches MockUser default) | ✅ |
| 6 | clientes | tests/routers/test_clientes_router.py | 1 | 1 | mock-skew: fixture row lacked `id` so `.eq("id", cliente_id).single()` returned None → 404 | Add `"id": "c1"` to fixture | ✅ |
| 7 | matching | tests/routers/test_matching_router.py | 1 | 1 | mock-skew: fixture rows lacked `embedding`/`status` so `.is_("embedding", "null").eq("status", "ativo")` excluded them → service called with empty list | Add `"embedding": None, "status": "ativo"` to fixture rows | ✅ |
| 8 | email_service | tests/services/test_email_service.py | 2 | 2 | same root cause as cluster 2 BUT these tests don't use the `client` fixture (construct `EmailService` directly) so the conftest patch doesn't reach them | Per-test `patch("noctusai_lib.config.credentials._get_public_client", return_value=db)` blocks | ✅ |
| 9 | bi_dashboard | tests/routers/test_bi_dashboard_router.py | 1 | 1 (covered `contratos_ativos` + `negociacoes_abertas` assertions) | mock-skew: fixture rows lacked `created_at` so `.gte("created_at", year_start)` filter excluded them | Add `"created_at": "2026-02-01T10:00:00"` to fixture rows | ✅ |
| 10 | portais | tests/routers/test_portais_router.py | 1 | 1 | mock-skew: fixture rows lacked `natureza`/`pronto_para_portais`/`status` so chained `.eq` predicates excluded them → generator called with empty list | Add `"natureza": "imovel", "pronto_para_portais": True, "status": "ativo"` to fixture rows | ✅ |
| 11 | site_imoveis | tests/routers/test_site_imoveis_router.py | 1 | 1 | mock-skew: site_config fixture lacked `slug` + `is_active`; ativos fixture lacked `org_id` so chained predicates returned None → 404 | Add missing predicate-fields to both fixtures | ✅ |

Σ **31 → 0 failed**, all fixes test-side, zero seed/app-code touches. Stable across 2 consecutive full-suite runs.

---

## Knowledge

- **K-1**: Architect-side env refresh resolved E-1 (stale starlette in shared site-packages) and E-2 (PROJECT.md not pushed). E's L-1/L-2/L-3 stand as durable lessons.
- **K-2**: `venv/bin/pytest` is canonical for this product; system pytest must NEVER be used.
- **K-3**: The seed `_get_public_client` boundary is the documented external-boundary mock target for credential-tier-1+2 lookups (`KB § PATTERNS/testing.md`; precedent file `test_standard_llm_smoke.py`'s `llm_client` fixture). Lifting the patch into the product-wide `client` fixture in conftest.py was the structural fix — drained clusters 2, 4 (emails) in one shot.

---

## Lessons

- **L-1 — Cluster 1's blast pattern is a useful diagnostic shape.** When 10 tests in one file all return "ignored / session_not_configured / unhandled_event" with identical logs, the failure is upstream of the per-test branches — a single short-circuit predicate. Reading the router once + the resolver once was enough to identify the missing 3 columns in the fixture; per-test inspection would have been wasted.
- **L-2 — Mock-skew is the dominant root-cause class in this baseline.** 9 of 11 clusters were "test fixture missing fields that production query filters on." The seed framework + StrictHttpModel absorptions tightened production queries while test fixtures stayed at the older, looser shape. The 2 remaining clusters were code-drift (configuracoes refactor to seed `chat_completion`) and seed-boundary-mock-missing (certidoes/emails).
- **L-3 — `_get_public_client` patching belongs at the product `client` fixture level, not per-test.** When the seed credentials module is involved (background tasks calling `resolve_credential`, routers using `require_credential_or_422`, services using `_get_resend_config`), every test that runs against the `client` fixture benefits from a single conftest-level patch. The precedent (`llm_client` per-test fixture) is correct for SCOPED tests, but for product-wide coverage the conftest patch is structurally cheaper.

---

## Slips

- **SL-1 — None this session.** All fixes stayed within the brief's authorized scope (`products/erp-imobiliario/backend/tests/**`). No app code touched; no seed touched; no out-of-scope cluster surfaced that needed seed/app changes.

---

## Errors

- **E-1 — `LLMAPIError("...")` ctor signature mismatch.** First fix attempt for `test_openai_chave_invalida` used 1-arg ctor; real signature is `(provider: str, message: str, status_code: int = 502)`. Caught by next test run, fixed in same iteration. Cheap (one-shot iteration), but reinforces: ALWAYS check exception ctor signature before patching with `side_effect=Exception(...)`.

---

## Mistakes

- (none)

---

## Methodology improvement spotted (LOUD)

**Architect-eyes / s1 candidate** — The 9-of-11 mock-skew cluster suggests an MCP-tool opportunity:

> A **`noctus.dev.scan_mock_predicate_skew`** keeper-style detector that, for each `set_table_data("<table>", [...])` call, statically infers the predicate-set the consuming router will apply (by walking the matching router/service via libcst) and flags fixtures missing any predicate-column. Stage-3 KB doc + Stage-4 detector. Recurrence is at N≥9 in this single project, suggesting it has been quietly accumulating across the platform.

Surfacing only, **not implementing** — out of brief scope. Architect routes to s1→s4 codification pipeline if it survives "does this pattern recur across products" check (`KB § PATTERNS/methodology-codification-pipeline.md`).
