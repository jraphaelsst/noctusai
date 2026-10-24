"""F80 (prod, 2026-10-24) — a certidão's estado civil comes from the
document's OWN kind and from a marriage actually read, never from the type
an operator filed it under.

A photographed CERTIDÃO DE NASCIMENTO ("À MARGEM DO TERMO NADA CONSTA", one
person) was uploaded as `certidao_casamento`; the casamento rules inferred
`casado`/`alta` from the KIND ("no averbação of divórcio/óbito") with only
the titular read and no regime/date — and the product applied it.

Synthetic, OCR-shaped texts only (every name/number invented).
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents import (
    AVISO_ESTADO_CIVIL_NAO_CORROBORADO,
    AVISO_TIPO_DOCUMENTO_DIVERGENTE,
    ExtractionConfidence,
    tipo_civil_divergente,
)
from noctusai_lib.integrations.documents.civil_status import ROTULO_CASADO_POR_CERTIDAO
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.types import TitularEsperado

NASCIMENTO_OCR = """
REPUBLICA FEDERATIVA DO BRASIL
REGISTRO CIVIL DAS PESSOAS NATURAIS
CERTIDÃO DE NASCIMENTO
NOME
CARLOS EDUARDO FICTICIO SANTOS
MATRÍCULA
123456 01 55 1980 1 00012 034 0005678-12
DATA DE NASCIMENTO
DOZE DE MARÇO DE MIL NOVECENTOS E OITENTA   12/03/1980
SEXO
MASCULINO
FILIAÇÃO
JOSE FICTICIO SANTOS
MARIA FICTICIA SANTOS
AVERBAÇÕES/ANOTAÇÕES À ACRESCER
À MARGEM DO TERMO NADA CONSTA
O conteúdo da certidão é verdadeiro. Dou fé.
São Paulo, 15 de abril de 2009
"""

#: A certidão de casamento of which the read recovered ONLY the titular —
#: no second spouse, no data do casamento, no regime, no averbação.
CASAMENTO_SO_TITULAR_OCR = """
REPUBLICA FEDERATIVA DO BRASIL
REGISTRO CIVIL DAS PESSOAS NATURAIS
CERTIDÃO DE CASAMENTO
NOMES
CARLOS EDUARDO FICTICIO SANTOS
CPF
529.982.247-25
"""

CASAMENTO_COMPLETO_OCR = """
REPUBLICA FEDERATIVA DO BRASIL
REGISTRO CIVIL DAS PESSOAS NATURAIS
CERTIDÃO DE CASAMENTO
NOMES
CARLOS EDUARDO FICTICIO SANTOS
CPF
529.982.247-25
ANA PAULA FICTICIA LIMA
CPF
111.444.777-35
DATA DE REGISTRO DO CASAMENTO POR EXTENSO
DEZ DE JUNHO DE DOIS MIL E DEZ
DIA
10
MÊS
06
ANO
2010
AVERBAÇÕES/ANOTAÇÕES À ACRESCER
NADA CONSTA
"""


class _StubResolved:
    def __init__(self, text=""):
        self.text, self.error, self.error_message = text, None, None


class _StubResolver:
    """DI stand-in for the vision rung (never a patch of our own code)."""

    def __init__(self, text: str):
        self._resolved = _StubResolved(text)

    async def resolve(self, media):
        return self._resolved


async def _ler(text: str, tipo: str, titular=None):
    return await LadderIdentityExtractor(resolver=_StubResolver(text)).extract(
        b"x", mimetype="image/jpeg", tipo_documento=tipo, titular=titular
    )


def _codigos(out) -> list[str]:
    return (out.aviso or "").split("+")


class TestTipoCivilDivergente:
    def test_nascimento_declared_casamento(self):
        assert tipo_civil_divergente("certidao_casamento", NASCIMENTO_OCR) == "certidao_nascimento"

    def test_same_kind_or_non_civil_declared_is_none(self):
        assert tipo_civil_divergente("certidao_nascimento", NASCIMENTO_OCR) is None
        assert tipo_civil_divergente("rg", NASCIMENTO_OCR) is None
        assert tipo_civil_divergente("certidao_casamento", "texto sem marcador") is None


class TestNascimentoFiledAsCasamento:
    @pytest.mark.asyncio
    async def test_flags_and_never_reads_casado(self):
        out = await _ler(NASCIMENTO_OCR, "certidao_casamento")
        assert AVISO_TIPO_DOCUMENTO_DIVERGENTE in _codigos(out)
        assert "certidão de nascimento, não de casamento" in (out.aviso_mensagem or "")
        assert "reenvie com o tipo certo" in (out.aviso_mensagem or "")
        assert out.estado_civil != "casado"
        assert out.estado_civil_rotulo != ROTULO_CASADO_POR_CERTIDAO
        assert out.tipo_provavel == "certidao_nascimento"

    @pytest.mark.asyncio
    async def test_read_as_a_birth_certificate(self):
        """Read with the nascimento rules: the emission date rides (freshness
        rules need it) and no casamento-only finder runs."""
        out = await _ler(NASCIMENTO_OCR, "certidao_casamento")
        assert out.data_emissao is not None and out.data_emissao.year == 2009
        assert out.conjuges == ()
        assert out.data_casamento is None


class TestCasadoNeedsTheMarriageRead:
    @pytest.mark.asyncio
    async def test_only_the_titular_read_is_a_suggestion(self):
        out = await _ler(
            CASAMENTO_SO_TITULAR_OCR,
            "certidao_casamento",
            titular=TitularEsperado(nome="CARLOS EDUARDO FICTICIO SANTOS"),
        )
        assert out.estado_civil == "casado"
        assert out.estado_civil_confianca is not ExtractionConfidence.ALTA
        assert AVISO_ESTADO_CIVIL_NAO_CORROBORADO in _codigos(out)
        assert AVISO_TIPO_DOCUMENTO_DIVERGENTE not in _codigos(out)

    @pytest.mark.asyncio
    async def test_a_real_casamento_is_unchanged(self):
        out = await _ler(CASAMENTO_COMPLETO_OCR, "certidao_casamento")
        assert out.estado_civil == "casado"
        assert out.estado_civil_confianca is ExtractionConfidence.ALTA
        assert AVISO_ESTADO_CIVIL_NAO_CORROBORADO not in _codigos(out)
        assert AVISO_TIPO_DOCUMENTO_DIVERGENTE not in _codigos(out)
