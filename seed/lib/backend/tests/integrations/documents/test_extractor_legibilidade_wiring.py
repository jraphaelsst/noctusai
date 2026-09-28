"""`LadderIdentityExtractor` wires `legibilidade.avaliar_legibilidade` into
its own `aviso`/`aviso_mensagem` — end to end, through `.extract()`, not just
the pure `avaliar_legibilidade` unit itself (see `test_legibilidade.py`).
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.legibilidade import AVISO_LEITURA_COMPROMETIDA
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.types import TextSource

#: A CPF whose check digits verify.
_CPF_VALIDO = "412.954.238-98"

#: The measured CNH-screenshot failure this closes (see `legibilidade.py`'s
#: module docstring): a hallucinated date, a hallucinated CEP, and the
#: holder's `NOME` landing on the mother's `FILIAÇÃO` name.
_CNH_SCREENSHOT_COMPROMETIDA = (
    "CNH DIGITAL\n"
    "NOME: MARIA APARECIDA DAS DORES\n"
    "DATA DE NASCIMENTO: BRASILEROCA\n"
    f"CPF: {_CPF_VALIDO}\n"
    "CEP: 99 de abril\n"
    "FILIACAO: JOSE DA SILVA E MARIA APARECIDA DAS DORES\n"
)

_CNH_LIMPA = (
    "CARTEIRA NACIONAL DE HABILITACAO\n"
    "NOME: JOAO CARLOS PEREIRA\n"
    "DATA DE NASCIMENTO: 12/05/1980\n"
    f"CPF: {_CPF_VALIDO}\n"
)


class _Ladder:
    """DI stand-in for `DocumentTextLadder` — same shape
    `test_identity_new_fields.py` uses, scripted for the text-layer rung
    only (no fallthrough needed for these fixtures)."""

    def __init__(self, camada: str, source: TextSource = TextSource.OCR):
        self.camada = camada
        self.source = source

    async def to_text(self, content, mimetype=None, filename=None, *, pular_camada_texto=False):
        return (self.camada, self.source, None)


class TestLegibilidadeWiredThroughExtract:
    @pytest.mark.asyncio
    async def test_compromised_reading_carries_the_aviso(self):
        ladder = _Ladder(_CNH_SCREENSHOT_COMPROMETIDA)
        out = await LadderIdentityExtractor(ladder=ladder).extract(
            b"fake-bytes", mimetype="image/jpeg"
        )
        assert out.leitura_comprometida is True
        assert AVISO_LEITURA_COMPROMETIDA in (out.aviso or "").split("+")
        assert out.aviso_mensagem and "conferencia humana obrigatoria" in out.aviso_mensagem

    @pytest.mark.asyncio
    async def test_clean_reading_is_not_flagged(self):
        ladder = _Ladder(_CNH_LIMPA)
        out = await LadderIdentityExtractor(ladder=ladder).extract(
            b"fake-bytes", mimetype="image/jpeg"
        )
        assert out.leitura_comprometida is False
        assert AVISO_LEITURA_COMPROMETIDA not in (out.aviso or "").split("+")
