# Proposal: Multi-provider LLM Phase 9 — wrap-up bundled improvements

**Agent:** claude-opus-4-7
**Origin:** project:multi-provider-llm:phase-9
**Generated:** 2026-04-19 14:01
**Severity:** low
**Effort:** low
**Affected products:** erp-imobiliario, therapy-platform, seed
**Status:** pending

---

## 1. Context

Phase 9 closed the backend side of the multi-provider-LLM consolidation: MASTER-PROMPTs (ERP/Therapy/seed) updated to point at `noctusai_lib.llm`; ERP pytest 1765✓/23 skip; Therapy pytest 1078✓; MCP review 0 issues on both; 3 ERP + 4 Therapy tests rewritten from mocked SDK internals to the shared-lib contract; 3 misnamed ERP dev benchmarks moved to `collect_ignore`.

---

## 2. Situation

The wrap-up revealed three categories of residual issue: (1) test-fixture discipline around the shared lib — some tests still patch internal implementation details rather than the lib's public surface or a FakeProvider; (2) the `--review` checks are clean today but rely on grep-based detection that won't catch future regressions like `import openai as _oai`; (3) the 3 misnamed dev benchmarks were left in `tests/` under `collect_ignore` rather than relocated to a proper `bench/` dir — a short-term fix rather than the clean move.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Each improvement hardens the boundary between product code and the shared lib, so future drift is caught earlier.

### 3.2 Application instructions

#### 1. Migrate remaining service tests to FakeProvider + LLMConfig

**Linkage:** The Phase-9 rewrites used `patch("<service>._lib_generate_embedding")` and `patch("noctusai_lib.llm.transcribe_audio")` — pragmatic but still monkeypatches at the import level. Task.md §3 principle #8 calls for FakeProvider via `LLMConfig` for service tests, same as the lib's own tests. Move these tests onto that pattern.

**Steps:**
1. Add a shared pytest fixture `fake_llm` in each product's `conftest.py` that installs a `FakeProvider` and `configure_llm(LLMConfig(provider=fake))`.
2. Rewrite the two ERP + four Therapy migrated tests to use the fixture and assert on `fake.calls` rather than patched symbols.
3. Delete the `patch("<service>._lib_generate_embedding")` usages.
4. Run both product pytest suites to confirm no regression.

**Risks:** Low — test-only change, covered by running the suites.

*Independent:* can be applied without other bundled improvements.

#### 2. Promote the grep invariants from success criteria into a CI check

**Linkage:** Task.md §9 lists the grep invariants (no `from openai import`, no `AsyncOpenAI(`, no `httpx.AsyncClient(.*openai.com)`). Today they live only as documentation. A pre-commit / CI check would catch re-introductions.

**Steps:**
1. Add a script `scripts/verify-llm-boundary.sh` that runs the grep patterns across `products/*/backend/app/services/`.
2. Hook it into the existing `scripts/pre-commit` hook chain (next to `verify-kb-sync.sh`).
3. Document the rule in `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` (§ `llm/`) so future contributors know why the script exists.

**Risks:** Low — script is read-only. If a legitimate non-LLM usage of `httpx` matches (e.g. a URL containing "openai" for unrelated reasons), tune the regex.

*Independent:* can be applied without other bundled improvements.

#### 3. Relocate the 3 dev benchmarks out of `tests/` into `bench/`

**Linkage:** `test_embedding_vs_rules.py`, `test_mock_matching_local.py`, `test_mock_matching_large.py` are dev scripts. `collect_ignore` hides them from pytest but leaves them in the test tree. Moving to `products/erp-imobiliario/backend/bench/` is the cleaner structural fix.

**Steps:**
1. Create `products/erp-imobiliario/backend/bench/` with a README explaining its purpose.
2. Move the 3 files there, updating their relative-path logic (they read `../.env`).
3. Remove the `collect_ignore` block from `tests/conftest.py`.
4. Update `test_embedding_vs_rules.py`'s `OPENAI_EMBEDDINGS_URL` / `EMBEDDING_MODEL` imports to use `noctusai_lib.llm.generate_embedding` so the benchmark actually runs.

**Risks:** Medium — touching the benchmark script; may break the batch progress-printing until it's ported to `generate_embedding` loop.

*Independent:* can be applied without other bundled improvements.

### 3.3 Seed APIs / shared lib involved

N/A — change is local to the product.

### 3.4 Risks before applying

Low — all bundled items are test/tooling-only; no production path affected.

### 3.5 Alternatives considered

N/A — the situation dictates the fix.

---

## 4. Effects

When this is applied, these change:

- **Coverage:** FakeProvider migration makes service tests exercise the real dispatch path, not mocks.
- **Risk profile:** CI grep check stops future raw-SDK re-introductions silently.
- **Ergonomics:** Moving bench scripts out of `tests/` ends the `collect_ignore` workaround.

---

## 5. Acceptance Criteria

- [ ] Fix applied to every affected product (not just the one that triggered detection)
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)
- [ ] `python mcp/noctusai/cli.py --review --product erp-imobiliario` files no new proposals for this issue
- [ ] Backend tests still pass for the affected product(s)
- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates
- [ ] Documentation updated KB-first, CLAUDE.md second (per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`)
- [ ] All product pytest suites green after FakeProvider migration
- [ ] CI grep script runs in <1s, documented in KB § `llm/`
- [ ] `bench/` dir created with updated scripts; `tests/conftest.py` has no `collect_ignore` for them

---

## 6. Related files

- `task.md` — Phase 9 (source phase).
- `products/erp-imobiliario/backend/tests/services/test_embedding_service.py` — FakeProvider migration target.
- `products/therapy-platform/backend/tests/services/test_transcription_service.py` — FakeProvider migration target.
- `products/therapy-platform/backend/tests/services/test_therapy_embedding_service.py` — FakeProvider migration target.
- `products/erp-imobiliario/backend/tests/conftest.py` — `collect_ignore` to remove once bench/ lands.
