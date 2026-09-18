-- 048_storage_no_public_buckets.sql — Migration: close the public-bucket data leak
-- Schema: erp
--
-- THE INCIDENT (found + live-mitigated 2026-09-17). `erp-certidoes` (102
-- objects / 21MB of CPF-bearing certidões — full names, debt/restriction
-- findings) and `erp-geral` (0 objects) were declared `public = true` in
-- `001_erp_imobiliario.sql` + `011_storage_buckets.sql` (both IMMUTABLE
-- HISTORY — NOT edited by this migration; this is the forward fix).
--
-- 🔴 `storage.objects` had RLS ENABLED with 17 policies (`erp_storage_*`,
-- org-scoped via the first path segment — see `035_rls_storage_current_
-- org_id.sql`) — and they gave ZERO protection, because Supabase Storage
-- serves a PUBLIC bucket's objects via the `/object/public/{bucket}/{path}`
-- route, which does not evaluate storage.objects RLS AT ALL (only the
-- `/object/authenticated/...` and `/object/sign/...` routes do). "RLS is
-- on" was a false sense of safety — anyone with (or able to guess/enumerate)
-- an object URL could fetch a certidão fully unauthenticated. The
-- tech-lead flipped both buckets to `public = false` LIVE on 2026-09-17
-- (leak closed); this migration is what makes that the declared, forward,
-- idempotent state, so a fresh environment (or Supabase re-reading 001/011's
-- `ON CONFLICT DO NOTHING` insert) can never silently reopen it.
--
-- THE RULE IS ABSOLUTE (owner directive, 2026-09-17): zero public buckets,
-- in every product, forever — NO exception, NO override, ever. The
-- sanctioned alternative is a short-TTL signed URL minted by an authorized,
-- org-scoped endpoint AT READ TIME — never a public bucket, never a
-- persisted URL. See `app.services.storage_service.StorageService.
-- get_signed_url`, `noctusai_lib.integrations.storage`
-- (`documento_store.py`'s `.url()`, `contratos_service.url_versao`), and
-- `KB § PATTERNS/backend/database-rls.md § Storage buckets — never public`.
-- Enforced going forward by `noctus.dev.check_storage_bucket_public`
-- (pre-commit, severity critical, no allowlist) and the live
-- `predeploy_check` `storage_bucket_public` leg (fails, never skips).
--
-- Idempotent: the bucket UPDATE is a no-op on re-run (`WHERE public =
-- true`); the column ADD is `IF NOT EXISTS`; the backfill UPDATE only
-- matches rows still carrying the old public-URL shape (already-migrated
-- rows have `arquivo_url IS NULL` and are skipped on a second run).

SET search_path = erp, public;

-- 1. Buckets — declared state now matches the live fix (public=false).
UPDATE storage.buckets
SET public = false
WHERE id IN ('erp-certidoes', 'erp-geral')
  AND public = true;

-- 2. `certidao_resultados` gains `arquivo_path` — the storage PATH
-- persisted instead of a URL. `arquivo_url` remains for the one
-- legitimate case it always could hold: the RAW InfoSimples site_receipt
-- URL, kept only when the file could not be copied into our own bucket
-- (see `app/services/certidoes_service.py::_process_single_certidao`).
-- Once a file IS in our bucket, its row carries `arquivo_path` and
-- `arquivo_url` is cleared — a signed URL is minted per-request at read
-- time (`app/routers/certidoes.py::_resolve_resultado_download_url`),
-- never persisted, never public.
ALTER TABLE erp.certidao_resultados
    ADD COLUMN IF NOT EXISTS arquivo_path text;

-- 3. Backfill the pre-existing rows whose `arquivo_url` is our own OLD
-- PUBLIC-bucket URL shape (`/object/public/erp-certidoes/{path}[?...]`,
-- 96 of 120 rows at time of writing) — move the path into `arquivo_path`,
-- clear `arquivo_url` (it is no longer a fetchable link now that the
-- bucket is private, and must not be served to a client as if it still
-- were). The query-string suffix (`get_public_url` appended `?...`) is
-- stripped. Idempotent: a second run finds no more `arquivo_url` rows
-- matching the pattern (already NULLed by the first).
UPDATE erp.certidao_resultados
SET
    arquivo_path = split_part(
        substring(arquivo_url from '/object/public/erp-certidoes/(.*)$'),
        '?', 1
    ),
    arquivo_url = NULL
WHERE arquivo_url LIKE '%/object/public/erp-certidoes/%';

NOTIFY pgrst, 'reload schema';
