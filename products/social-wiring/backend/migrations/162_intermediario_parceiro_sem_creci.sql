-- ============================================================================
-- Migration 162 · social_wiring: `atendimento_intermediarios.natureza` — a
-- commission-split recipient that is NOT a contracted, CRECI-qualified party
--
-- CONTRACT 08's OWN COMMISSION CLAUSE HAS THIS SHAPE ALREADY
-- --------------------------------------------------------------------------
-- "CLÁUSULA — DA INTERMEDIAÇÃO" contracts the VENDEDORA with TWO qualified
-- companies/people ("as empresas a seguir qualificadas") — each carrying a
-- CRECI number or a CNPJ+representante-corretor qualification. Its payment
-- paragraph then splits the agreed corretagem across THREE beneficiaries: the
-- same two qualified parties, PLUS a third company that receives a smaller
-- cut (5%) and is NEVER qualified anywhere in the instrument — it appears
-- exactly once, as a plain bank-deposit line ("por meio de depósito bancário
-- em favor de <razão social>, CNPJ <n>, <banco>...") in the split paragraph.
-- That third party is not a licensed real-estate broker and carries no CRECI
-- — a referral/partnership arrangement the seller and the two contracted
-- brokers agreed to share a slice of THEIR commission with.
--
-- `contrato_gerador._intermediacao` (derivacao.py) required `creci` on EVERY
-- `atendimento_intermediarios` row unconditionally, PF or PJ, with or without
-- `corretor_id` — so adding that third party the way the schema already
-- allows (nome + tipo/valor + favorecido_id, `creci` genuinely NULL) made
-- `avaliacao.pronto` false and blocked `gerar()` outright (`ContratoIncompleto`,
-- `service.py::gerar`). The only way to generate the contract was to leave
-- the third party out of `atendimento_intermediarios` altogether — which is
-- exactly the state that produced a generated commission clause 2 parties /
-- R$ 82.650 wide instead of the signed reference's 3 parties / R$ 87.000.
--
-- 🔴 EXTENDS THE EXISTING TABLE, NOT A PARALLEL ONE
-- --------------------------------------------------------------------------
-- A commission-split recipient IS an `atendimento_intermediarios` row in
-- every way that matters to the generator: it has a `nome`, a `tipo`/`valor`
-- share of the commission, and a `favorecido_id` naming who the money is
-- deposited to. `natureza` is the ONLY thing that differs — whether the row
-- is one of the CONTRACTED, QUALIFIED parties ('intermediario', the existing
-- and default meaning of every row this table has ever held) or a bare
-- split beneficiary that is never qualified in the clause header
-- ('parceiro_split'). A second table would duplicate `tipo`/`valor`/
-- `favorecido_id` and the split-sum/percentage-total logic that already
-- iterates `atendimento_intermediarios` wholesale (108's `pct_comissao`
-- divergence check, the split-payment paragraph) for zero benefit — both
-- kinds are summed and paid exactly the same way; only the readiness gate
-- and the qualification-header rendering branch on `natureza`.
--
-- `papel` IS METADATA, NEVER RENDERED
-- --------------------------------------------------------------------------
-- Free text ("indicação", "parceria comercial", "sócio da originadora") for
-- the operator's own record of WHY this party shares the commission. The
-- reference contract's split paragraph names the beneficiary and its bank
-- details only — no role/description phrase precedes it — so `papel` is
-- never interpolated into `contrato_gerador`'s output; it exists purely so
-- the CRM itself does not have to re-derive "who is this and why do they get
-- paid" from a bank-deposit line months later.
--
-- 🔴 NO DB CHECK CONSTRAINT HERE — VALIDATED AT THE API/SERVICE LAYER ONLY
-- --------------------------------------------------------------------------
-- Every rule a CHECK would express here is already enforced ABOVE the row:
-- `IntermediarioCreateBody.natureza` is a Pydantic `Literal["intermediario",
-- "parceiro_split"]` — an invalid value 422s before the service ever runs,
-- the same guarantee a `CHECK (natureza IN (...))` gives, one layer earlier.
-- `negociacao_estruturada_service._validar_natureza` refuses (named 400)
-- pairing `corretor_id` with `natureza='parceiro_split'` — the office's own
-- in-house corretor is always a qualified party by definition (`contexto.py`
-- qualifies `Imobiliaria` whenever any row carries a `corretor_id`).
-- `IntermediarioCreateBody.papel`'s `max_length=160` caps the free text
-- before it is ever written. NOC-REMEDIATE[atendimento-intermediarios-
-- natureza-check]: when this migration is APPLIED, pair it with a genuine
-- `verify_db_guards` probe (`_insert_check_probe` against the three rules
-- above) and add the matching `CHECK`s at the same time — deferred rather
-- than shipped un-probed (a structural CHECK with no proof it refuses
-- anything is exactly the "verified to EXIST, never verified to REFUSE"
-- gap `noctus.dev.verify_db_guards` exists to close, and this migration is
-- file-only today: applying it later is the tech-lead's + user's decision;
-- see `migrations/APPLIED.md`). — 2026-09-23
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimento_intermediarios
    ADD COLUMN IF NOT EXISTS natureza TEXT NOT NULL DEFAULT 'intermediario',
    ADD COLUMN IF NOT EXISTS papel    TEXT;

COMMENT ON COLUMN social_wiring.atendimento_intermediarios.natureza IS
    '''intermediario'' (default): a contracted party the header qualifies '
    '(CRECI required) — the only meaning this table had before 162. '
    '''parceiro_split'': a commission-split beneficiary that is never '
    'qualified in the clause header and never required to carry a CRECI '
    '(a company or person sharing a cut of the commission, not a licensed '
    'broker). Both kinds are summed into the split total the same way. '
    'Validated at the API layer (Pydantic Literal) + service layer '
    '(_validar_natureza) — see this migration''s header for why there is '
    'no matching DB CHECK yet.';
COMMENT ON COLUMN social_wiring.atendimento_intermediarios.papel IS
    'Free-text role/reason the operator records for a ''parceiro_split'' '
    'row (e.g. ''indicação'', ''parceria comercial''). Never rendered into '
    'the generated contract — see this migration''s header.';
