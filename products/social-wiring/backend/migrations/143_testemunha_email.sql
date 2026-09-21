-- ============================================================================
-- Migration 143 · social_wiring: org_testemunhas gains e-mail — the office's
-- real signed contracts print it, and D4Sign needs it to send a witness
-- ============================================================================
-- WHAT THIS IS FOR
-- ----------------
-- `org_testemunhas` (migration 108) shipped `nome`/`cpf`/`rg` only. The
-- office's own reference contract (`contracts/08 - REV FINAL_... - Card no
-- Sistema.docx`, the F5 template spec's §2.17 clause + §3 placeholder rows
-- 87-89) prints each witness as NOME + E-MAIL + RG — never CPF — and
-- `f5-template-spec.md` §5.1 already lists "exactly 2 org_testemunhas with
-- `nome` + `rg`" as the hard-required pair, with e-mail spec row 89 marked
-- optional. The *implementation* had drifted from that already-written spec:
-- `contrato_gerador` printed CPF instead of RG and had no e-mail column to
-- read at all, so a configured witness could never be added to a D4Sign
-- envelope (`assinatura_service.enviar` requires every signatário's
-- `email`). See `KNOWLEDGE-BASE/CONTEXT/PRODUCTS/social-wiring/
-- CONTRACT-FIELD-PROVENANCE-MAP.md` § "Testemunhas" for the corrected
-- provenance row.
--
-- WHAT CHANGES
-- ------------
-- One nullable, optional column. `cpf`/`rg` are UNCHANGED — CPF remains an
-- optional field an office MAY hold for a witness (validated when present,
-- never required), RG remains the identifying document the contract prints
-- and the readiness gate now requires (see `contrato_gerador/derivacao.py`'s
-- `_imobiliaria` — this migration does not touch that Python-side rule).
-- ============================================================================

ALTER TABLE social_wiring.org_testemunhas
    ADD COLUMN IF NOT EXISTS email TEXT;

COMMENT ON COLUMN social_wiring.org_testemunhas.email IS
    'Optional — required only to add this witness as a papel=''testemunha'' '
    'signatário in a D4Sign envelope (`assinatura_service.enviar`, which '
    'resolves it authoritatively from this registry by nome match), never '
    'to print or generate the contract itself (migration 143).';
