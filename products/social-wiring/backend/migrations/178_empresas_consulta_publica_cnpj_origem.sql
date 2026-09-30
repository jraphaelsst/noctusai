-- ============================================================================
-- 178 — `empresas.dados_origem` gains a documented fourth machine value:
--        `consulta_publica_cnpj` (a public CNPJ registry lookup)
-- ============================================================================
--
-- WHY
-- ---
-- Owner decision (2026-09-30, verbatim): "the system must resolve by itself;
-- humans only when it truly can't" — and a company's `situação cadastral` is
-- PUBLIC data. Live prod test, 5 real deals: every empresa a party holds a
-- participação in (auto-created from a Serasa Crednet report, migration 167)
-- sat with `situacao_cadastral IS NULL` until a human uploaded its Cartão
-- CNPJ; 8 companies across those 5 deals, only 3 Cartões on file. From this
-- dispatch on, `card_hub.crednet_service` resolves it automatically off a
-- public CNPJ registry (`noctusai_lib.integrations.cnpj_registry` — BrasilAPI
-- primary, ReceitaWS fallback) the moment an empresa is created, and
-- `empresas.consulta_publica_scheduler`'s hourly sweep catches up whatever
-- that first attempt missed. The office's own Cartão CNPJ upload keeps
-- precedence — this is a fill-empty stopgap, never a substitute for it.
--
-- WHY A MIGRATION FOR A VALUE THAT NEEDS NO SCHEMA CHANGE
-- ---------------------------------------------------------
-- Migration 167 left `empresas.dados_origem` a bare `TEXT` — no DB CHECK
-- constrains its values (§A.1's own comment: "shape-only" is `cnpj`'s own
-- CHECK, not this column's). But that migration's `COMMENT ON COLUMN` DOES
-- document the closed set of values every reader/writer is expected to
-- agree on (`serasa_crednet | cartao_cnpj | manual | certidao_consulta`) —
-- the one place this vocabulary is written down at all. Per this repo's own
-- "documentation IS the contract when there is no DB-enforced one" posture,
-- adding a FOURTH value to that vocabulary without updating the comment
-- would leave the column's own documentation silently wrong the moment this
-- ships — so this migration updates ONLY that comment, forward-only,
-- touching no rows and no constraint.
--
-- Forward-only, idempotent: `COMMENT ON COLUMN` is not additive/subtractive
-- DDL (it fully replaces the prior comment text, which is exactly the
-- point — the old text is superseded, not lost: it lives in migration 167's
-- own history). No `ALTER TABLE ... ADD/DROP`, no data touched.

SET search_path = social_wiring, public;

COMMENT ON COLUMN social_wiring.empresas.dados_origem IS
    'serasa_crednet | cartao_cnpj | manual | certidao_consulta (backfill) | '
    'consulta_publica_cnpj (migration 178: a public CNPJ registry lookup, '
    'BrasilAPI/ReceitaWS — fill-empty only, a Cartão CNPJ always outranks '
    'it) — who wrote the GROUP of cadastral fields. Machine-pending iff '
    'origem <> manual AND dados_confirmado_em IS NULL (migration 167).';
