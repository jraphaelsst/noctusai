"""🔴 LOCAL TEST DOUBLE — NOT the seed module.

`noctusai_lib.integrations.documents.{serasa_crednet,cartao_cnpj}` is S1's
deliverable (a SIBLING worktree/branch — `feat/sw-p0c-seed-extractors`, per
the P0c contract `sw-drive-extraction-P0c-contract.md` §B), not yet merged
into THIS worktree. This module is the "clearly marked minimal local test
double" the contract's brief sanctions for exactly this situation — it
mirrors §B's dataclass shapes and `.extract()` Protocol calling convention
byte-for-byte, so `crednet_service` / `app.modules.empresas.extracao_service`
production code (written against those §B names/signatures) is exercised
here the SAME way it will be once S1 lands, via dependency injection — never
a monkeypatch of production code (`KB § PATTERNS/compliance/testing.md`).

DELETE THIS FILE once S1 has merged and import the real dataclasses/
extractors from `noctusai_lib.integrations.documents.{serasa_crednet,
cartao_cnpj}` instead — every test importing from here should then import
from there, unchanged in shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Mapping, Optional

from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource

ALTA = ExtractionConfidence.ALTA
BAIXA = ExtractionConfidence.BAIXA
NENHUMA = ExtractionConfidence.NENHUMA

#: Synthetic, valid-check-digit CPF/CNPJ — same values the seed's OWN test
#: suite already uses as its canonical examples
#: (`seed/lib/backend/tests/integrations/documents/test_{cpf,cnpj}.py`).
CPF_VALIDO = "41295423898"
CPF_VALIDO_OUTRO = "52998224725"
CPF_INVALIDO = "41295423899"  # same digits, wrong DV — deliberately invalid

CNPJ_VALIDO = "11222333000181"
CNPJ_VALIDO_OUTRO = "12345678000195"
CNPJ_VALIDO_TERCEIRO = "98765432000198"
CNPJ_INVALIDO = "11222333000199"  # same digits, wrong DV — deliberately invalid


# ─── Serasa Crednet (§B) ─────────────────────────────────────────────────


@dataclass(frozen=True)
class OcorrenciaCrednet:
    constam: Optional[bool] = None
    quantidade: Optional[int] = None
    valor: Optional[object] = None  # Decimal in the real module
    ultimo_registro: Optional[date] = None


_SEM_OCORRENCIA = OcorrenciaCrednet(constam=False, quantidade=0)


@dataclass(frozen=True)
class ParticipacaoCrednet:
    razao_social: Optional[str] = None
    cnpj: Optional[str] = None
    cnpj_valido: bool = False
    participacao_pct: Optional[object] = None  # Decimal in the real module
    uf: Optional[str] = None
    situacao_texto: Optional[str] = None
    #: Crednet's own "SITUAÇÃO DO CNPJ EM" — NOT a closing date (contract
    #: E2). Never trusted as `empresas.data_situacao_cadastral`.
    situacao_em: Optional[date] = None
    desde: Optional[str] = None
    confianca: ExtractionConfidence = NENHUMA


@dataclass(frozen=True)
class CrednetFields:
    consulta_em: Optional[datetime] = None
    protocolo: Optional[str] = None
    cpf: Optional[str] = None
    cpf_valido: bool = False
    nome: Optional[str] = None
    nome_mae: Optional[str] = None
    data_nascimento: Optional[date] = None
    cpf_situacao: Optional[str] = None
    cpf_situacao_em: Optional[date] = None
    pendencias_internas: OcorrenciaCrednet = _SEM_OCORRENCIA
    pendencias_financeiras: OcorrenciaCrednet = _SEM_OCORRENCIA
    protesto_estadual: OcorrenciaCrednet = _SEM_OCORRENCIA
    cheques_sem_fundo: OcorrenciaCrednet = _SEM_OCORRENCIA
    participacoes: tuple[ParticipacaoCrednet, ...] = ()
    confiancas: Mapping[str, ExtractionConfidence] = field(default_factory=dict)
    rotulos: Mapping[str, Optional[str]] = field(default_factory=dict)
    source: TextSource = TextSource.NENHUMA
    aviso: Optional[str] = None
    error: Optional[str] = None
    error_message: Optional[str] = None

    def ocorrencias_constam(self) -> Optional[bool]:
        """True — any of the four constam; False — all four explicitly
        False; None — at least one is unreadable (`constam is None`) and
        none is True (§B's own three-state contract)."""
        estados = (
            self.pendencias_internas.constam,
            self.pendencias_financeiras.constam,
            self.protesto_estadual.constam,
            self.cheques_sem_fundo.constam,
        )
        if any(e is True for e in estados):
            return True
        if all(e is False for e in estados):
            return False
        return None


class FakeCrednetExtractor:
    """Deterministic, obviously-synthetic extractor — the dev/test default,
    mirroring `FakeMatriculaExtractor`'s posture."""

    async def extract(self, content: bytes, *, mimetype=None, filename=None) -> CrednetFields:
        if not content:
            return CrednetFields(error="empty_document", error_message="no bytes to read")
        return CrednetFields(
            consulta_em=datetime(2026, 9, 1, 12, 0, 0),
            protocolo="9999999",
            cpf=CPF_VALIDO,
            cpf_valido=True,
            nome="FULANA DE TESTE",
            nome_mae="CICLANA DE TESTE",
            data_nascimento=date(1990, 1, 1),
            pendencias_internas=OcorrenciaCrednet(constam=False, quantidade=0),
            pendencias_financeiras=OcorrenciaCrednet(constam=False, quantidade=0),
            protesto_estadual=OcorrenciaCrednet(constam=False, quantidade=0),
            cheques_sem_fundo=OcorrenciaCrednet(constam=False, quantidade=0),
            participacoes=(
                ParticipacaoCrednet(
                    razao_social="EMPRESA TESTE LTDA",
                    cnpj=CNPJ_VALIDO,
                    cnpj_valido=True,
                    participacao_pct=50,
                    uf="SP",
                    confianca=ALTA,
                ),
            ),
            source=TextSource.TEXT_LAYER,
        )


@dataclass(frozen=True)
class ScriptedCrednetExtractor:
    """Returns a pre-built `CrednetFields` (or a whole list, one per call,
    for a re-extraction scenario) — the fine-grained double `crednet_
    service`'s own tests inject through DI to assert the D1 apply / empresa
    upsert / conflict-opening logic precisely."""

    fields: CrednetFields

    async def extract(self, content: bytes, *, mimetype=None, filename=None) -> CrednetFields:
        return self.fields


# ─── Cartão CNPJ (§B) ────────────────────────────────────────────────────


@dataclass(frozen=True)
class CartaoCnpjFields:
    cnpj: Optional[str] = None
    cnpj_valido: bool = False
    matriz_filial: Optional[str] = None  # Literal['MATRIZ', 'FILIAL'] in the real module
    data_abertura: Optional[date] = None
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    porte: Optional[str] = None
    natureza_juridica: Optional[str] = None
    #: Normalized lower, in the 116 vocab (`ativa|baixada|inapta|suspensa|
    #: nula`), else None (raw value rides in `rotulos`).
    situacao_cadastral: Optional[str] = None
    #: "DATA DA SITUAÇÃO CADASTRAL" — the trustworthy closing date (E2),
    #: unlike Crednet's `situacao_em`.
    data_situacao_cadastral: Optional[date] = None
    motivo_situacao: Optional[str] = None
    #: 🔴 SCOPE CUT (owner decision, 2026-09-24): no address fields — see
    #: `app.modules.empresas.dados_service`'s module docstring.
    uf: Optional[str] = None
    emitido_em: Optional[datetime] = None
    confiancas: Mapping[str, ExtractionConfidence] = field(default_factory=dict)
    rotulos: Mapping[str, Optional[str]] = field(default_factory=dict)
    source: TextSource = TextSource.NENHUMA
    aviso: Optional[str] = None
    error: Optional[str] = None
    error_message: Optional[str] = None


class FakeCartaoCnpjExtractor:
    """Deterministic, obviously-synthetic extractor — the dev/test default."""

    async def extract(self, content: bytes, *, mimetype=None, filename=None) -> CartaoCnpjFields:
        if not content:
            return CartaoCnpjFields(error="empty_document", error_message="no bytes to read")
        return CartaoCnpjFields(
            cnpj=CNPJ_VALIDO,
            cnpj_valido=True,
            matriz_filial="MATRIZ",
            data_abertura=date(2010, 1, 1),
            razao_social="EMPRESA TESTE LTDA",
            nome_fantasia="TESTE",
            porte="ME",
            natureza_juridica="206-2 - Sociedade Empresária Limitada",
            situacao_cadastral="ativa",
            data_situacao_cadastral=None,
            uf="SP",
            emitido_em=datetime(2026, 9, 1, 9, 0, 0),
            source=TextSource.TEXT_LAYER,
        )


@dataclass(frozen=True)
class ScriptedCartaoCnpjExtractor:
    """Returns a pre-built `CartaoCnpjFields` — the fine-grained double
    `app.modules.empresas.extracao_service`'s own tests inject through DI."""

    fields: CartaoCnpjFields

    async def extract(self, content: bytes, *, mimetype=None, filename=None) -> CartaoCnpjFields:
        return self.fields


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
    "CartaoCnpjFields",
    "CrednetFields",
    "FakeCartaoCnpjExtractor",
    "FakeCrednetExtractor",
    "OcorrenciaCrednet",
    "ParticipacaoCrednet",
    "ScriptedCartaoCnpjExtractor",
    "ScriptedCrednetExtractor",
]
