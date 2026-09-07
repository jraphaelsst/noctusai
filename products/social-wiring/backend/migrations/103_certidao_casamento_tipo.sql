-- 103_certidao_casamento_tipo.sql
--
-- `certidao_casamento` as a first-class document type.
--
-- 🔴 WHY IT NEEDS ITS OWN TYPE INSTEAD OF `outro`.
-- ------------------------------------------------
-- Three certidões de casamento are already attached to a real atendimento in
-- this org, all filed as `outro`. `identidade_extracao_service.deve_extrair`
-- gates on the type, so `outro` means no extraction is ever SCHEDULED for
-- them — the single richest source of qualificação civil we hold sits unread.
--
-- A certidão de casamento is the ONLY document in the corpus that answers
-- "estado civil" and "regime de bens", which are the two fields that decide
-- whether a spouse must sign the instrument. CC art. 1.647: a sale without a
-- required outorga conjugal is anulável.
--
-- 🔴 AND THE READING RULE IS PART OF THE TYPE, NOT AN OPTION.
-- -----------------------------------------------------------
-- Page 1 of a certidão is the marriage: a LABELLED form, stating "regime de
-- bens: comunhão parcial" in exactly the shape a field-grabbing parser reads
-- first. The AVERBAÇÃO — divorce, name reversion — is prose, further in.
--
-- Measured on the three documents we hold (2026-09-07): ALL THREE parties are
-- divorced, and ALL THREE certidões say "casado, comunhão parcial" on page 1.
-- A parser that stops early does not lose information; it returns the
-- opposite of the truth, with a labelled field to back it up.
--
-- So this type is registered together with `TIPOS_LEITURA_INTEGRAL` in
-- `identidade_extracao_service`, which forces `max_pages=None` on the vision
-- rung. Registering the type without that rule would be worse than leaving it
-- as `outro`: it would start writing confident wrong answers where today it
-- writes nothing.
--
-- LGPD: `identidade`. A certidão carries filiação, CPF and civil status for
-- two people — the same category as an RG, and it inherits the same retention
-- policy by carrying the same `categoria_lgpd`.
--
-- Idempotent: safe to re-run.

SET search_path = social_wiring, public;

INSERT INTO social_wiring.cliente_documento_tipos
    (tipo_documento, categoria_lgpd, descricao, ativo)
VALUES
    ('certidao_casamento', 'identidade',
     'Certidão de casamento (com averbações) — estado civil e regime de bens',
     TRUE)
ON CONFLICT (tipo_documento) DO UPDATE
    SET categoria_lgpd = EXCLUDED.categoria_lgpd,
        descricao      = EXCLUDED.descricao,
        ativo          = TRUE;
