-- ============================================================================
-- 194 — per-part provenance for the bairro (extraction defect, 2026-10-03)
--
-- Live prod test: two buyers on one deal had logradouro/número/cidade/UF/CEP
-- off their comprovante de endereço and NO bairro, so the contract gate said
-- "Endereço completo" was missing (a signed contract prints the bairro). The
-- seed CEP lookup (F3, ViaCEP/BrasilAPI — already the authority for
-- cidade/UF) returns a bairro for most street-level CEPs; when the document
-- itself carries none, the bairro is now filled from that lookup.
--
-- The `endereco_*` group has ONE provenance quintet (153). A bairro that came
-- from the CEP lookup and not from the document the group's `endereco_origem`
-- names must say so, or a human auditing the address cannot tell a printed
-- bairro from a looked-up one. `endereco_bairro_origem`:
--   NULL  -> the bairro (if any) came from the same source as the group
--            (`endereco_origem`) — every row written before this migration;
--   'cep' -> filled from the CEP lookup because the document printed none;
--   <tipo_documento> -> a later document supplied ONLY the bairro the group
--            was missing (or replaced a 'cep' bairro — a document's bairro
--            always wins over the lookup's, whose names are often generic).
-- TEXT, not a CHECK: the same open vocabulary every `*_origem` column on
-- clientes uses (074's rationale).
-- Forward-only, idempotent, no data touched.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS endereco_bairro_origem TEXT;

COMMENT ON COLUMN social_wiring.clientes.endereco_bairro_origem IS
    'Provenance of endereco_bairro ALONE when it differs from endereco_origem '
    '(194): NULL = same source as the group | ''cep'' = CEP lookup (the '
    'document printed no bairro) | <tipo_documento> = a later document '
    'supplied only the bairro.';
