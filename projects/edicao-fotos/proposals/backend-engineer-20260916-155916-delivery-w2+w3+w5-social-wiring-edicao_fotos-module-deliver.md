## Delivery: W2 + W3 + W5 (`products/social-wiring/backend/app/modules/edicao_fotos/`)

Branch `feat/ef-w2-sw-module` (base `1e8cf1f7`). It merges into `origin/dev` with no conflicts, including the W10a merge. Not pushed; the tech-lead integrates.

### Shipped
- **Module:** `register()` added to `MODULES`, with 19 routes under `/api/edicao-fotos`.
  - Sections: capacidades, configuracoes (org + plataforma), curadores, modelos, lotes, revisao.
  - Roles come from the trusted database, per contract §1.
  - Org scoping is enforced in `deps.py`, because the engine's client is a service-role client.
- **`services/ports.py`:** wires the engine to real adapters.
  - The repository gets the public-default core client; jobs get the social_wiring admin client.
  - Storage is the `edicao-fotos` bucket through `BucketPhotoStorage`.
  - Image edits go through `openai_image_edit_factory(resolve_credential)`.
  - Also wired: the LLM structured adapter, BCB fx, the in-app notifier, and the per-org `DefaultingQuotaTracker`.
- **Worker:** started in `app/lifespan.py` only when `EDICAO_FOTOS_WORKER_ENABLED` is set (default OFF). A startup failure is isolated and logged at ERROR.
- **Body-size overrides:** `/api/edicao-fotos/lotes/*/fotos` = 256 MB (derived: 10 files × 25 MB). `/api/edicao-fotos/referencias` = 52 MB, declared ahead of the W6 route.
- **Response shapes:** match the seed FE hooks (W10a). They are pinned by `seed/lib/frontend/src/photo-editing/contract.fixture.json`, which the backend replays against the live routes.
- **Seed additions** (small, consumer-driven):
  - permissions: `list_grants`, `add_grant`, `remove_grant`
  - engine repo: `list_batches`, `save_org_settings`, `update_platform_settings`, `photo_states_for_batches`, and an InMemory `id_factory`
  - engine ports: `BucketPhotoStorage`
  - quota: `DefaultingQuotaTracker`
  - `dashboard` value changed to `'platform'`
- **Contract §0:** corrected to the seed's flat error shape `{detail, code}`.

### Verification
- social-wiring suite: 4389 passed (rc 0)
- seed lib suite: 4637 passed, 1 skipped (rc 0)
- keepers `upload-route-body-override`, `no-self-monkeypatch`, `every-test-file-is-gated`, `verify-kb-sync` and `seed-declared-imports`: all rc 0
- module tests:
  - strict 401 on all 19 routes (enumerated from `register()`)
  - one role-matrix 403 row per route, with a completeness assertion
  - cross-org 404 on every batch route
  - a full upload → submit → seed Worker → review → decide → zip run through the routes

### Deferred
Each deferred item has a named destination.
- W4 Econômico (C8). It is refused with `economico_indisponivel`.
- W6: reference pool and guides. **Until W6 ships, no guide can be activated through the API, so `submeter` returns 409 `guia_nao_ativo`.**
- W7: rules.
- W8: model metrics and notes. `/modelos` returns them as null.
- W9: dashboard.
- Email and WhatsApp notifications, plus agency-admin opt-ins: `NOC-REMEDIATE[edicao-fotos-notify-channels]`.
- Scheduler jobs: `fotos.daily_model_notes` and the fx backfill cron.
- `fotos.regen_guia` and `fotos.propor_regras` are enqueued by the engine, but they only run once the worker is enabled.
