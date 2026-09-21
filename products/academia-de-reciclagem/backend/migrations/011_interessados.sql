-- ============================================================================
-- Migration 011 — Interessados (public "receber futuras comunicações" signup)
--
-- Contract: products/academia-de-reciclagem/projects/interessados-CONTRACT.md
-- ("Data — academia_de_reciclagem.interessados"). The fleet's first
-- unauthenticated WRITE route (POST /api/public/interessados) lands
-- through the backend's service-role client — never through PostgREST
-- directly — so this table needs NO `anon` grant and NO `authenticated`
-- policy: the ONLY caller is this product's own backend.
--
-- No `org_id` — public visitors have no org; this table is product-level,
-- not org-scoped (unlike every table in 006_knowledge.sql).
--
-- Column names are PT-BR per the contract's own Data table
-- (`consentimento_versao`, `consentimento_em`, `criado_em`,
-- `atualizado_em`) — a deliberate departure from this product's other
-- tables' EN `created_at`/`updated_at` convention (006/007/008), because
-- the contract is authored and is the source of truth for this table
-- specifically. `academia_de_reciclagem.set_updated_at()` (006) is NOT
-- reused here for that reason — it hardcodes `NEW.updated_at`.
--
-- Forward-only + idempotent (CREATE TABLE/INDEX IF NOT EXISTS, DROP POLICY
-- IF EXISTS before CREATE POLICY, CREATE OR REPLACE FUNCTION/TRIGGER),
-- matching the platform convention. NOT applied to any database by this
-- slice — the tech-lead applies it (see the A1/A2 dispatch precedent in
-- 006/007's own headers).
-- ============================================================================

SET search_path = academia_de_reciclagem, public;

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.interessados (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome                    TEXT NOT NULL,
    whatsapp                TEXT NOT NULL,
    email                   TEXT NOT NULL,
    origem                  TEXT,
    consentimento_versao    TEXT NOT NULL,
    consentimento_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Contract: "UNIQUE on `lower(email)`" — an expression index, not a plain
-- column constraint, so it also catches a row written with a differently
-- cased email by any future code path, not just the normal one (the
-- backend always lower-cases before writing — see `app/interessados/pg.py`
-- — this is defence in depth). PostgREST's `.upsert(on_conflict=...)`
-- cannot target an expression index, so the store does its own
-- select-then-insert-or-update instead of relying on this index for the
-- upsert path (see that module's docstring).
CREATE UNIQUE INDEX IF NOT EXISTS interessados_email_lower_key
    ON academia_de_reciclagem.interessados (lower(email));

-- Supports the admin listing's `ORDER BY criado_em DESC` (contract:
-- "GET /api/interessados ... newest first").
CREATE INDEX IF NOT EXISTS interessados_criado_em_idx
    ON academia_de_reciclagem.interessados (criado_em DESC);

ALTER TABLE academia_de_reciclagem.interessados ENABLE ROW LEVEL SECURITY;

-- Service-role only. `authenticated` still carries the schema-wide
-- default-privilege table GRANT from 001_academia-de-reciclagem.sql, but
-- RLS enabled with ONLY this policy is an implicit deny for every other
-- role — the same shape 010_anon_grant_lockdown.sql documents for
-- `kb_revisions`. No `authenticated` policy is added: admin access is
-- gated in the API layer (`require_scopes(..., user_roles=ADMIN)`), never
-- via a direct PostgREST/RLS path, per contract §B.0's precedent (every
-- route in this product reads/writes through the admin client).
DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.interessados;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.interessados
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Explicit redundant REVOKE — keeps "no anon grant" true by inspection of
-- THIS file alone, rather than relying on 010's `ALTER DEFAULT PRIVILEGES`
-- having already flipped the schema default for objects created after it
-- (same role, later migration — true today, but this line costs nothing
-- and removes the doubt for a future reader of this file in isolation).
REVOKE ALL ON academia_de_reciclagem.interessados FROM anon;

-- `atualizado_em` gets its own trigger function (not the shared
-- `set_updated_at()` from 006, which hardcodes `NEW.updated_at`) because
-- this table's column name is PT-BR per the contract.
CREATE OR REPLACE FUNCTION academia_de_reciclagem.set_interessados_atualizado_em()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$ BEGIN NEW.atualizado_em = now(); RETURN NEW; END; $$;

CREATE OR REPLACE TRIGGER set_atualizado_em_interessados
    BEFORE UPDATE ON academia_de_reciclagem.interessados
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.set_interessados_atualizado_em();
