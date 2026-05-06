-- ============================================================
-- 027 — Rename plans columns to PT-BR (mirror products convention)
-- ============================================================
-- The plans table was the only public schema table that mixed PT-BR
-- product copy with English column names — the same drift class that
-- caused the on_license_change outage (migration 026). Rename to mirror
-- products: name → nome, description → descricao, is_active → ativo.
--
-- Scope: 3 column renames; no data migration needed (rename preserves
-- values + FKs + indexes). is_custom kept (different shape — opaque flag,
-- not a display field).
-- ============================================================

ALTER TABLE public.plans RENAME COLUMN name TO nome;
ALTER TABLE public.plans RENAME COLUMN description TO descricao;
ALTER TABLE public.plans RENAME COLUMN is_active TO ativo;
