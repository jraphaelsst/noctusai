"""Shared test doubles for the P0c Crednet/Cartão CNPJ document extractors.

`noctusai_lib.integrations.documents.{serasa_crednet,cartao_cnpj}` (S1) is
merged into this worktree — every dataclass and Fake extractor comes from
there, unchanged, per DI (`KB § PATTERNS/compliance/testing.md`). This module
is NOT a stand-in for the seed; it only re-exports the seed's own
`FakeCrednetExtractor`/`FakeCartaoCnpjExtractor` — both now accept `result=`
to script a specific outcome, the same convention `fake.FakeIdentityExtractor`
already used (mirrored onto both P0c Fakes rather than reinventing a local
"Scripted*Extractor" pair: `FakeCrednetExtractor(result=fields)` /
`FakeCartaoCnpjExtractor(result=fields)` IS the scripted double now) — plus a
few synthetic, checksum-valid CPF/CNPJ constants tests share.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.cartao_cnpj import (
    CartaoCnpjExtractor,
    CartaoCnpjFields,
    FakeCartaoCnpjExtractor,
    make_cartao_cnpj_extractor,
    parse_cartao_cnpj,
)
from noctusai_lib.integrations.documents.serasa_crednet import (
    CrednetExtractor,
    CrednetFields,
    FakeCrednetExtractor,
    OcorrenciaCrednet,
    ParticipacaoCrednet,
    make_crednet_extractor,
    parse_crednet,
)
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource

ALTA = ExtractionConfidence.ALTA
BAIXA = ExtractionConfidence.BAIXA
NENHUMA = ExtractionConfidence.NENHUMA

#: Synthetic, valid-check-digit CPF/CNPJ, ALREADY NORMALIZED (no punctuation)
#: — the shape `empresas.cnpj` (migration 167's `^[0-9A-Z]{12}[0-9]{2}$`
#: CHECK) and `crednet_service`/`dados_service`'s own `normalize_cnpj(...)`
#: calls store/compare against. Same digits the seed's OWN Fakes use as
#: their canonical formatted examples
#: (`seed/lib/backend/noctusai_lib/integrations/documents/{serasa_crednet,
#: cartao_cnpj,fake}.py`), just without the punctuation a DB row/assertion
#: here never carries.
CPF_VALIDO = "41295423898"
CPF_VALIDO_OUTRO = "52998224725"
CPF_INVALIDO = "41295423899"  # same digits, wrong DV — deliberately invalid

CNPJ_VALIDO = "11222333000181"
CNPJ_VALIDO_OUTRO = "12345678000195"
CNPJ_VALIDO_TERCEIRO = "98765432000198"
CNPJ_INVALIDO = "11222333000199"  # same digits, wrong DV — deliberately invalid

__all__ = [
    "ALTA",
    "BAIXA",
    "CNPJ_INVALIDO",
    "CNPJ_VALIDO",
    "CNPJ_VALIDO_OUTRO",
    "CNPJ_VALIDO_TERCEIRO",
    "CPF_INVALIDO",
    "CPF_VALIDO",
    "CPF_VALIDO_OUTRO",
    "NENHUMA",
    "CartaoCnpjExtractor",
    "CartaoCnpjFields",
    "CrednetExtractor",
    "CrednetFields",
    "FakeCartaoCnpjExtractor",
    "FakeCrednetExtractor",
    "OcorrenciaCrednet",
    "ParticipacaoCrednet",
    "TextSource",
    "make_cartao_cnpj_extractor",
    "make_crednet_extractor",
    "parse_cartao_cnpj",
    "parse_crednet",
]
