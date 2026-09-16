## Delivery: W6 — `/referencias` + `/guias` (+ the two admin pages)

Branch `feat/ef-w6-pool-guides` (base `c536e01b`, which includes the W2+W3+W5 merge). Committed; not pushed — the tech-lead integrates.

### R1 unblock (no OpenAI)
A platform admin or curator can now write a guide by hand and activate it. After that, `POST /lotes/{id}/submeter` no longer returns 409 `guia_nao_ativo`. The steps:
1. `POST /api/edicao-fotos/guias {"texto": "..."}` returns 201 with a draft.
2. `POST /api/edicao-fotos/guias/1/ativar` returns 200.

`test_manual_guide_unblocks_submission_without_the_ai_builder` covers this end to end, with zero LLM calls.

### Routes (8 new; module total 27)
All eight require a platform admin or a `photo_curator` grant. Anyone else gets 403 `restrito_curadoria`.
- `GET /referencias?page&page_size&incluir_arquivadas` returns the page plus `pool{pares_ativos, limite_pares, cheio}` and `opcoes{comodos, tipos_edicao}`.
- `POST /referencias` (multipart): files `antes` and `depois`, form fields `comodo`, `tipos_edicao[]` and `nota`.
  - Returns 201, or 409 `pool_cheio` when the pool is full.
  - Uses the 52 MB override that was already declared; its comment in `main.py` now shows how the 52 MB is derived.
- `DELETE /referencias/{id}` archives the pair (idempotent) and returns it.
- `GET /guias` · `POST /guias` (manual draft) · `POST /guias/regenerar` (202; 409 `pool_vazio` on an empty pool) · `POST /guias/{versao}/ativar` · `POST /guias/{versao}/restaurar` (201).
- `PUT /configuracoes/plataforma` now accepts `limite_pares_referencia` (null or 0 means unlimited). The limit is only written when the field is sent.

### Seed additions (consumer-driven)
- **New `photo_editing.pool`:** `add_reference_pair`, `archive_reference_pair`, `pool_status`.
  - Both images are normalized and GPS-stripped before storage.
  - The pair is stored as keys in the private bucket.
  - If the insert is refused, the stored objects are deleted again.
- **`pipeline.request_guide_regen`:** a manual job that runs immediately.
  - The handler skips the pool-settling debounce for `manual` payloads.
  - A 60 s dedupe window makes a double click one job.
- **`PhotoEditingPorts.reference_storage`:** the guide builder now sends the stored bytes; a missing object raises an error.
- **Repository additions:** `add_reference`, `get_reference`, `archive_reference` (compare-and-set), `count_active_references`, `list_references`, `list_guides`.
  - Implemented in the Protocol, in-memory and Supabase versions.
  - The Supabase version maps the migration-129 trigger error to `PoolFullError`.
- **Types:** `PlatformSettings.limite_pares_referencia`, `PoolFullError`, `dedupe_regen_guia_manual`.
- **Frontend:**
  - Hook factory: multipart `useCriarReferencia`, a paged `useReferencias` that returns pool state, guide hooks, and platform-settings hooks.
  - `ReferencePairCard`: optional `formatComodo` / `formatTipoEdicao` label props.
  - Contract fixture: 10 new entries, replayed by the backend tests.
- **Shared test setup:** `seed/framework/frontend/vitest.setup.ts` now provides a no-op `ResizeObserver`. This is the recurrence rule at N=3; the local copy in `Settings.test.tsx` was removed.

### Migration 129 (FILE ONLY — applying it needs owner consent)
`129_fotos_pool_limite.sql` does two things:
- adds `fotos_platform_settings.limite_pares_referencia`;
- adds a `BEFORE INSERT / un-archive` trigger that locks the settings row and refuses a pair past the limit.

🔴 **Until 129 is applied, sending `limite_pares_referencia` from `PUT /configuracoes/plataforma` fails at PostgREST** (the column is missing). Everything else in W6 works on the applied 121–128.

### Frontend
- New pages `Referencias` (`/edicao-fotos/referencias`) and `GuiasEstilo` (`/edicao-fotos/guias`).
  - Both have `NAV_GROUPS` and `NAV_FALLBACK` entries whose routes match the 128 `status_pagina` names (`edicao-fotos-referencias`, `edicao-fotos-guias`).
  - Both lock themselves unless the caller's capabilities allow it.
  - The limit editor appears only for platform admins.
- Fixed on contact:
  - `Configuracoes.tsx` sent `virtual_staging`, but the backend literal is `staging_virtual`, so saving with that box checked returned 422. It now uses the shared `rotulos.ts`.
  - The `ConnectionDetailDialog` loading gate used `isLoading`; it now follows the two-signal rule.

### Verification
- social-wiring backend: 4423 passed (`--timeout=180`, rc 0)
- seed lib backend: 4647 passed, 1 skipped (rc 0)
- SW vitest: 1554 passed (rc 0); SW tsc rc 0; SW vite build succeeded
- seed lib vitest (photo-editing): 27 passed; seed lib tsc rc 0
- framework vitest: 57 passed
- keepers:
  - upload-route-body-override, no-self-monkeypatch, every-test-file-is-gated and verify-kb-sync: rc 0
  - lying-loading-state: rc 0, with 1 remaining pre-existing warning in erp-imobiliario `Campo.tsx`, which is not this product

### Deferred
- Applying migration 129 (needs owner consent).
- Running the AI builder live (no OpenAI credits; PROJECT.md §4c).
- Automatic regeneration only runs with `EDICAO_FOTOS_WORKER_ENABLED`, as W2 set up.
