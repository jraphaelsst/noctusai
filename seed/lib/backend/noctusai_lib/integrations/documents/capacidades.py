"""Per-document-type extraction capability catalog.

`CAPACIDADES` answers, for a given `tipo_documento`, which CANONICAL fields
a SEED-shipped parser can lift off it — independent of any product's own
storage schema or provenance policy. It is the seed-side half of a
product's own file → field provenance catalog (e.g.
`products/social-wiring/backend/app/modules/card_hub/proveniencia/fontes.py`,
which knows its OWN `tipo_documento` vocabulary and column names and checks
its claims against this one: `Fonte.campos ⊆ CAPACIDADES[Fonte.tipo_documento]`).

**Why a seed module, not a product one.** The alternative — leaving "what
can an RG photo tell me" implicit in each product's own extraction service
— is how `card_hub/identidade_extracao_service.py`'s `TIPOS_EXTRAIVEIS` and
`imovel_hub/documentos_service.py`'s `TIPOS_EXTRAIVEIS` ended up as two
independently hand-maintained literal sets answering overlapping questions
(one product, two files) with no test tying either back to what the
extractor it calls actually produces. This module is the ONE place that
answer lives; a product's own `TIPOS_*` constants — the subset it has
CHOSEN to persist, which may be narrower than what is readable — are
re-derived from its own catalog, which is in turn checked against this one.

**Canonical field names mirror the typed carrier that produces them** —
`IdentityFields` (`types.CAMPOS`, plus the two attributes that dataclass
deliberately keeps OUT of `CAMPOS` because they are not independently
persistable columns of their own — see that tuple's docstring) and the
matrícula header parser (`matricula.find_matricula`) — NOT a product's
database column names, which are free to differ (`clientes.nome_oficial`
vs. this module's `"nome"`; `clientes.rg_orgao_expedidor` vs. `"rg_orgao"`).
A product's own catalog is where that renaming is declared, once, in one
place a test can walk.

**Scope, honestly.** This module currently catalogues the two seed
extractors social-wiring's contract-gate wave (migrations 153/154) put to
work: the identity-document reader (`factory.make_identity_extractor`) and
the matrícula header's `find_matricula`. The FULL matrícula parse
(`make_matricula_extractor` — cartório, inscrição, ônus, atos, the whole
transcription) is a materially larger seed capability this module does not
yet catalogue field-by-field.
NOC-REMEDIATE[capacidades-matricula-completa]: extend `CAPACIDADES["matricula"]`
once a product needs its own `Fonte` to claim one of those fields — 2026-09-23.
The imóvel CND/guia-IPTU structured reads
(`imovel_hub/documentos_service.py`'s `extrair_estrutura`) are a per-product
ad-hoc LLM JSON prompt, not a seed-typed parser, so they are deliberately
absent here too — see that product module's own `CAMPOS_ESTRUTURA_POR_TIPO`.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.types import CAMPOS as _IDENTITY_CAMPOS

#: Every `IdentityFields` attribute a label-anchored finder can lift off a
#: full identity document, PLUS `rg_orgao` (read beside the RG number,
#: `rg.py`) and `data_emissao` (the document's own issuance date, read by
#: `civil_status.py`'s averbação pass) — both deliberately excluded from
#: `types.CAMPOS` because they are not INDEPENDENTLY persistable columns
#: (see that tuple's docstring), not because they cannot be read.
_IDENTIDADE_COMPLETA: frozenset[str] = frozenset(_IDENTITY_CAMPOS) | {
    "rg_orgao",
    "data_emissao",
}

#: `tipo_documento -> {canonical field names a seed parser can lift off it}`.
#:
#: Read-only vocabulary — nothing here writes to a product's database, and
#: nothing here asserts a product MUST persist everything it lists; it only
#: bounds what a product's own `Fonte.campos` may claim.
CAPACIDADES: dict[str, frozenset[str]] = {
    # `factory.make_identity_extractor` over an RG (old model or CIN) or a
    # CNH photo/PDF (text-layer -> vision fallback, `ladder.py`).
    "rg": _IDENTIDADE_COMPLETA,
    "cnh": _IDENTIDADE_COMPLETA,
    # A CPF card carries only the number (and, rarely, a printed name) — no
    # birthdate/estado-civil/etc. worth claiming.
    "cpf": frozenset({"nome", "cpf"}),
    # Full-document read (a product's own `TIPOS_LEITURA_INTEGRAL`, per
    # `types.IdentityFields`' own note on averbação timelines): the margin
    # carries estado_civil/regime_bens/data_casamento readings beside the
    # identity ones, and `conjuges.py` links the other spouse named on it.
    "certidao_casamento": _IDENTIDADE_COMPLETA | {"conjuge"},
    "certidao_nascimento": _IDENTIDADE_COMPLETA,
    # Address-only, by what the document is evidence OF (`address.py`) — a
    # utility bill's printed name/CPF belong to whoever it was mailed to,
    # not necessarily this titular, so this module does not claim them even
    # though nothing stops a caller from reading the bytes further.
    "comprovante_endereco": frozenset({"endereco"}),
    # `matricula.find_matricula` — the número de matrícula off the header.
    # See the module docstring's scope note for the full-parse gap.
    "matricula": frozenset({"numero_matricula"}),
}
