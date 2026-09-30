"""The vision/OCR fallback for a ficha cadastral bancária with no usable
AcroForm data (a flattened copy, or — measured on the P3 corpus,
2026-09-30 — a scanned FGTS form with no text layer and no fillable
fields at all).

🔴 SINGLE-PERSON ONLY, DELIBERATELY SCOPED
--------------------------------------------
`ficha_cadastral.py`'s widget-driven rung reads however many people a
fillable form names, each attributed to their OWN page. Once a form has
degraded to narrative OCR text, that page-per-person structure is gone —
telling two people's qualification paragraphs apart in raw vision output
is exactly the multi-person segmentation problem `conjuges.py` solves for
a certidão de casamento, and reusing it here would assume a certidão's own
layout (a `NOMES` block, `FILIACAO` markers) a bank form does not share.

The forms this rung actually serves are single-person by construction
(the FGTS declaration is one person's own statement) — so this module
reads the WHOLE text as ONE person and stops there. A multi-person
comprador/vendedor form that reaches this rung (its OWN AcroForm was
somehow stripped) would only surface its FIRST person; that gap is
real and left named rather than silently covered — `NOC-REMEDIATE
[ficha-cadastral-texto-multi-pessoa]` — a future pass adds page-window
segmentation the same way `financiamento_imobiliario.py`'s `paginas=`
narrowing does, if a real corpus ever needs it.

Every value here is tempered to `BAIXA` at best (never `ALTA`) — this text
came off a vision pass, not a PDF's own AcroForm data or text layer; see
`matricula_extractor.py`'s own note on why anything short of exact digital
data is demoted for a field with no independent plausibility check.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.address import find_endereco
from noctusai_lib.integrations.documents.birthdate import find_birthdate
from noctusai_lib.integrations.documents.civil_status import find_estado_civil
from noctusai_lib.integrations.documents.cpf import find_cpf
from noctusai_lib.integrations.documents.ficha_cadastral import (
    ALTA,
    BAIXA,
    NENHUMA,
    FichaCadastralLida,
    PessoaFichaCadastral,
)
from noctusai_lib.integrations.documents.nacionalidade import find_nacionalidade
from noctusai_lib.integrations.documents.name import find_name
from noctusai_lib.integrations.documents.profession import find_profissao
from noctusai_lib.integrations.documents.types import ExtractionConfidence


def _temperar(confianca: str) -> ExtractionConfidence:
    return BAIXA if confianca in ("alta", "baixa") else NENHUMA


def parse_texto(text: str) -> FichaCadastralLida:
    """One person's worth of fields off narrative (OCR/vision) text. Pure,
    never raises — a document with none of these fields yields a
    `FichaCadastralLida` with an empty `pessoas` tuple, not an error (a
    legible document may simply not carry a field, same posture every
    sibling parser in this package takes)."""
    nome, _nome_conf, _ = find_name(text)
    cpf, _cpf_conf, _ = find_cpf(text)
    nascimento, _nasc_conf, _ = find_birthdate(text)
    estado_civil, _ec_conf, _ = find_estado_civil(text)
    nacionalidade, _nac_conf, _ = find_nacionalidade(text)
    profissao, _prof_conf, _ = find_profissao(text)
    endereco = find_endereco(text)

    if not (nome or cpf):
        return FichaCadastralLida(pessoas=())

    pessoa = PessoaFichaCadastral(
        papel=None,
        nome=nome, nome_confianca=_temperar(_nome_conf) if nome else NENHUMA,
        cpf=cpf, cpf_confianca=_temperar(_cpf_conf) if cpf else NENHUMA,
        data_nascimento=nascimento,
        data_nascimento_confianca=_temperar(_nasc_conf) if nascimento else NENHUMA,
        estado_civil=estado_civil,
        estado_civil_confianca=_temperar(_ec_conf) if estado_civil else NENHUMA,
        nacionalidade=nacionalidade,
        nacionalidade_confianca=_temperar(_nac_conf) if nacionalidade else NENHUMA,
        profissao=profissao,
        profissao_confianca=_temperar(_prof_conf) if profissao else NENHUMA,
        endereco=endereco if endereco.presente else None,
    )
    return FichaCadastralLida(pessoas=(pessoa,))


__all__ = ["parse_texto"]
