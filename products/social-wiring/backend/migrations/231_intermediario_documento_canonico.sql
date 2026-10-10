-- ============================================================================
-- 231 — atendimento_intermediarios: document CHECKs accept the CANONICAL
-- (punctuated) form the service has written since 2026-10-01
-- ============================================================================
--
-- THE BUG. Migration 114 pinned `documento` and `representante_cpf` to BARE
-- digits (`^[0-9]{11}$`, `^[0-9A-Z]{12}[0-9]{2}$`). The canonical-identifiers
-- change (556ec1ed7, owner rule 2026-10-01: "the canonical form of every
-- document number is its PUNCTUATED form") made the service store
-- `111.444.777-35` / `11.222.333/0001-81` (`_normalizar_documento`,
-- `representante_cpf` → `ident_primitives.canonico`). Every save of an
-- intermediary WITH a document since then is refused by the database
-- (SQLSTATE 23514). Production on 2026-10-10: the 3 rows carrying a document
-- all predate 10-01; the 2 created that day carry none.
--
-- WHY THE SUITE STAYED GREEN. The mock did not know these CHECKs. Since
-- 2026-10-10 `MockSupabaseClient` enforces migration-declared cross-column
-- CHECKs (`noctusai_lib.testing.sql_check`) — that is what surfaced this.
--
-- THE FIX follows the owner rule (punctuated IS canonical) rather than
-- reverting the service. ORDER (load-bearing): drop the old digits-only
-- CHECKs → rewrite the 3 bare rows to the canonical form → add the
-- punctuated CHECKs. The first version rewrote rows UNDER the old CHECK and
-- failed its prod apply with 23514 (2026-10-10; rolled back, never recorded). Shape only, as in 114 — check digits stay the service's job.
-- Readers are unaffected: the contract generator reads digits back out
-- (`frases.documento` → `so_digitos`). Idempotent.
-- ============================================================================

SET search_path = social_wiring, public;

-- 1. Drop 114's digits-only CHECKs FIRST.
ALTER TABLE social_wiring.atendimento_intermediarios
    DROP CONSTRAINT IF EXISTS atendimento_intermediarios_documento_formato;
ALTER TABLE social_wiring.atendimento_intermediarios
    DROP CONSTRAINT IF EXISTS atendimento_intermediarios_representante_cpf_formato;

-- 2. Backfill: bare → canonical punctuated (only rows still bare). Runs with
--    NO document CHECK in place — under 114's digits-only CHECK the very
--    first rewritten row is refused (23514), which is exactly how the first
--    prod apply of this file failed (2026-10-10, rolled back cleanly).
UPDATE social_wiring.atendimento_intermediarios
   SET documento = regexp_replace(documento, '^([0-9]{3})([0-9]{3})([0-9]{3})([0-9]{2})$', '\1.\2.\3-\4')
 WHERE pessoa_tipo = 'pf' AND documento ~ '^[0-9]{11}$';

UPDATE social_wiring.atendimento_intermediarios
   SET documento = regexp_replace(
           documento,
           '^([0-9A-Z]{2})([0-9A-Z]{3})([0-9A-Z]{3})([0-9A-Z]{4})([0-9]{2})$',
           '\1.\2.\3/\4-\5')
 WHERE pessoa_tipo = 'pj' AND documento ~ '^[0-9A-Z]{12}[0-9]{2}$';

UPDATE social_wiring.atendimento_intermediarios
   SET representante_cpf = regexp_replace(
           representante_cpf, '^([0-9]{3})([0-9]{3})([0-9]{3})([0-9]{2})$', '\1.\2.\3-\4')
 WHERE representante_cpf ~ '^[0-9]{11}$';

-- 3. The CHECKs, now on the canonical shapes (validated against the
--    rewritten rows as they are added).
ALTER TABLE social_wiring.atendimento_intermediarios
    ADD CONSTRAINT atendimento_intermediarios_documento_formato
    CHECK (
        documento IS NULL
        OR (pessoa_tipo = 'pf' AND documento ~ '^[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}$')
        OR (pessoa_tipo = 'pj' AND documento ~ '^[0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3}/[0-9A-Z]{4}-[0-9]{2}$')
    );

ALTER TABLE social_wiring.atendimento_intermediarios
    ADD CONSTRAINT atendimento_intermediarios_representante_cpf_formato
    CHECK (representante_cpf IS NULL OR representante_cpf ~ '^[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}$');

COMMENT ON COLUMN social_wiring.atendimento_intermediarios.documento IS
    'CPF (pessoa_tipo=pf) or CNPJ (pj, alphanumeric allowed) in the CANONICAL '
    'punctuated form (111.444.777-35 / 11.222.333/0001-81, migration 231), '
    'check digits verified by the service. LGPD: identificação — never logged.';
COMMENT ON COLUMN social_wiring.atendimento_intermediarios.representante_cpf IS
    'CPF of the legal representative signing for a PJ intermediary, canonical '
    'punctuated form (migration 231). LGPD: identificação — never logged.';
