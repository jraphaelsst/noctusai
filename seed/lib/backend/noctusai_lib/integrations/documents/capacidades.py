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

**Scope, honestly.** This module currently catalogues the three seed
extractors social-wiring's contract-gate wave (migrations 137/153/154) put
to work: the identity-document reader (`factory.make_identity_extractor`),
the matrícula header's `find_matricula`, and the matrícula ACT TEXT's party
qualification reader (`matricula_qualificacao.extrair_qualificacoes`) — a
second, independent extraction over the SAME `tipo_documento="matricula"`
upload, on the SAME `origem="matricula"` write value, so it lands in
`CAPACIDADES["matricula"]` beside the header fields rather than under a
second key (there is no second physical document type to key it by).
`rg`/`rg_orgao_expedidor` from a matrícula qualification are genuinely
narrower than an identity document's — no photo, no `data_emissao` — but the
canonical names are the same ones `_IDENTIDADE_COMPLETA` already uses, so no
new vocabulary is introduced for them. The FULL matrícula parse
(`make_matricula_extractor` — cartório, inscrição, ônus, the rest of the
transcription beyond what a qualification or the header carries) remains a
materially larger seed capability this module does not yet catalogue
field-by-field; extend `CAPACIDADES["matricula"]` again once a product needs
its own `Fonte` to claim one of those. The imóvel CND/guia-IPTU structured
reads (`imovel_hub/documentos_service.py`'s `extrair_estrutura`) are a
per-product ad-hoc LLM JSON prompt, not a seed-typed parser, so they are
deliberately absent here too — see that product module's own
`CAMPOS_ESTRUTURA_POR_TIPO`.
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

#: `matricula_qualificacao.extrair_qualificacoes`' per-party read off the act
#: text — canonical names already shared with `_IDENTIDADE_COMPLETA`
#: (`"rg_orgao"` for the issuer, matching `types.CAMPOS`' vocabulary, not
#: `clientes.rg_orgao_expedidor`'s column name — see this module's own
#: docstring on why product columns are free to differ). `"endereco"` is
#: read (`Qualificacao.endereco`, unstructured prose) but a product may
#: choose NOT to auto-apply it to a structured column — see social-wiring's
#: `matriculas.qualificacao_service.CAMPOS_QUALIFICACAO` docstring for why
#: it deliberately does not yet; this catalogue only bounds what CAN be
#: read, same as every other entry here.
_QUALIFICACAO_MATRICULA: frozenset[str] = frozenset(
    {"profissao", "estado_civil", "nacionalidade", "rg", "rg_orgao", "endereco", "genero"}
)

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
    # `matricula.find_matricula` (the número off the header) PLUS
    # `matricula_qualificacao.extrair_qualificacoes` (each party's own
    # facts off the act text) — two independent readers, one
    # `tipo_documento`. See the module docstring's scope note for the
    # full-transcription gap this still does not cover.
    "matricula": frozenset({"numero_matricula"}) | _QUALIFICACAO_MATRICULA,
    # `serasa_crednet.parse_crednet` — a Serasa Crednet consulta (P0c
    # contract §B). Canonical names mirror `CrednetFields`' own scalar
    # attributes, plus `participacoes` and `ocorrencias` for the two
    # compound facts (`CrednetFields.participacoes` /
    # `.ocorrencias_constam()` + the four `Ocorrencia*` rows) — neither is a
    # single scalar column, so social-wiring's own `Fonte.campos` claims
    # them as one name each rather than enumerating their sub-fields.
    "serasa_crednet": frozenset(
        {
            "nome", "cpf", "data_nascimento", "nome_mae", "protocolo",
            "consulta_em", "participacoes", "ocorrencias",
        }
    ),
    # `cartao_cnpj.parse_cartao_cnpj` — a Receita Cartão CNPJ (P0c contract
    # §B). Canonical names mirror `CartaoCnpjFields`' own attributes.
    "cartao_cnpj": frozenset(
        {
            "cnpj", "razao_social", "nome_fantasia", "porte",
            "natureza_juridica", "matriz_filial", "data_abertura",
            "situacao_cadastral", "data_situacao_cadastral",
            "motivo_situacao", "uf", "emitido_em",
        }
    ),
    # `guia_itbi.parse_guia_itbi` — a municipal Guia de ITBI (negociação/
    # financiamento extraction contract §D). Canonical names mirror
    # `GuiaItbiFields`' own attributes. `valor_venal`/`base_calculo`/
    # `valor_financiado_sfh` are claimable READS — that module's own header
    # documents why none of them may be mapped onto a negociação's
    # `valor_negociado`.
    "guia_itbi": frozenset(
        {
            "valor_transacao", "valor_venal", "base_calculo",
            "valor_financiado_sfh", "aliquota_pct", "valor_itbi",
            "vencimento", "inscricao_imobiliaria", "numero_matricula",
            "compradores", "vendedores", "municipio",
        }
    ),
    # `financiamento_imobiliario.parse_financiamento_imobiliario` — ONE
    # parser, TWO `tipo_documento` keys, because the contract (25 pages) and
    # the bank proposta (one photo) print the SAME Quadro Resumo vocabulary
    # (see that module's header). Canonical names mirror
    # `FinanciamentoImobiliarioFields`' own attributes; `conta_credito_
    # vendedor` is the owner-approved (H5) seller-account read.
    "contrato_financiamento": frozenset(
        {
            "banco_nome", "banco_codigo", "numero_contrato", "numero_proposta",
            "data_documento", "valor_compra_venda", "valor_avaliacao",
            "valor_financiado", "valor_fgts", "valor_recursos_proprios",
            "prazo_meses", "taxa_nominal_aa", "taxa_efetiva_aa",
            "sistema_amortizacao", "compradores", "vendedores",
            "conta_credito_vendedor",
        }
    ),
    "proposta_financiamento": frozenset(
        {
            "banco_nome", "banco_codigo", "numero_contrato", "numero_proposta",
            "data_documento", "valor_compra_venda", "valor_avaliacao",
            "valor_financiado", "valor_fgts", "valor_recursos_proprios",
            "prazo_meses", "taxa_nominal_aa", "taxa_efetiva_aa",
            "sistema_amortizacao", "compradores", "vendedores",
            "conta_credito_vendedor",
        }
    ),
}
