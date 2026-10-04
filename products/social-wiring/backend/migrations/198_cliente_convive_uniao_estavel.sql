-- ============================================================================
-- 198 — "convive em união estável" beside the estado civil (P5, deal 867)
--
-- `clientes.estado_civil` holds ONE value — the person's legal status. União
-- estável is not a change of legal status: a divorced seller who lives with a
-- companion is still "divorciado", and the office's signed contracts say both
-- ("FULANO, brasileiro, divorciado, …, que convive em união estável com
-- FULANA, brasileira, solteira, …" — signed deal 867). With one column the
-- operator had to choose between the true status and the companionship.
--
-- `convive_uniao_estavel` = this person lives in união estável with the person
-- linked as `conjuge_cliente_id`, WHILE `estado_civil` keeps their legal
-- status (solteiro/divorciado/viúvo/separado). The contract generator pairs
-- the two in one núcleo, prints each one's own estado civil, and treats the
-- couple exactly like `estado_civil = 'uniao_estavel'` everywhere else
-- (núcleo checks; a companion is not a certificando unless the office policy
-- says so). `casado` + this flag is refused by the generator, not by a CHECK
-- here: the record may be mid-edit.
--
-- (196 = certidão releitura; 197 left to the parallel extraction slice.)
-- Forward-only, idempotent; existing rows read FALSE, i.e. unchanged.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS convive_uniao_estavel BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN social_wiring.clientes.convive_uniao_estavel IS
    'Lives in união estável with conjuge_cliente_id while estado_civil keeps '
    'the legal status (solteiro/divorciado/viúvo/separado) — the contract '
    'prints both (198).';
