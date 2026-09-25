"""G17 (P1/883, 2026-09-25) — a `data_nascimento` that makes the party a
minor AT THE MARRIAGE DATE PRINTED ON THE SAME DOCUMENT is never written.

Real, measured: an image-only phone-scan certidão de casamento's vision
transcription put a spouse's birth year at a value that would make them
younger than 16 (CC art. 1.517's absolute marriageable-age floor, mirroring
`birthdate.MIN_AGE`) on the marriage date the SAME document names. Neither
`birthdate.find_birthdate`'s own sanity gate (checks a date only against
TODAY) nor a bare label match can catch this — they each look at only one
of the two dates. Comparing `data_nascimento` against `data_casamento` is
the check that does, and it lives in `real.LadderIdentityExtractor._ler`
(after both are resolved, including a spouse-selected `data_nascimento` via
`conjuges.find_conjuges`).

Values below are invented; `CERTIDAO_ANONIMIZADA` mirrors the wording shape
of `test_extractor_certidao_casamento.py`'s own fixture.
"""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.types import TextSource, TitularEsperado


class _Ladder:
    """DI stand-in for `DocumentTextLadder` — text-layer rung only, no
    vision call needed for these fixtures."""

    def __init__(self, texto: str) -> None:
        self.texto = texto

    async def to_text(self, content, mimetype=None, filename=None, *, pular_camada_texto=False):
        return (self.texto, TextSource.TEXT_LAYER, None)


#: A marriage on 10/06/2020; the first spouse's spelled-out birth year makes
#: them 14 on that date (born 2006) — implausible, a minor at marriage.
CERTIDAO_CONJUGE_IMPLAUSIVEL = """
CERTIDÃO DE CASAMENTO

NOMES

CARLOS EDUARDO SANTOS

CPF
111.222.333-44

FERNANDA LIMA OLIVEIRA

CPF
555.666.777-88

NOMES COMPLETOS DE SOLTEIRO, DATAS DE NASCIMENTO, NATURALIDADE, NACIONALIDADE E FILIAÇÕES DOS CÔNJUGES

CARLOS EDUARDO SANTOS, nascido no dia dez de maio de dois mil e seis (10/05/2006), em São Paulo, SP, de nacionalidade brasileira, filho de JOSE SANTOS e de MARIA SANTOS.
FERNANDA LIMA OLIVEIRA, nascida no dia vinte de abril de mil novecentos e noventa (20/04/1990), em São Paulo, SP, de nacionalidade brasileira, filha de PEDRO OLIVEIRA e de ANA OLIVEIRA.

Casaram-se em 10/06/2020, sob o regime de comunhão parcial de bens.
"""

#: Same shape, but the first spouse's birth year (1990) is plausible at the
#: 2020 marriage date — the control case this guard must NOT reject.
CERTIDAO_CONJUGE_PLAUSIVEL = CERTIDAO_CONJUGE_IMPLAUSIVEL.replace(
    "dez de maio de dois mil e seis (10/05/2006)",
    "dez de maio de mil novecentos e noventa (10/05/1990)",
)


class TestRejectsAnImplausibleSpouseBirthdate:
    @pytest.mark.asyncio
    async def test_a_dn_making_the_spouse_a_minor_at_marriage_is_not_written(self) -> None:
        out = await LadderIdentityExtractor(
            ladder=_Ladder(CERTIDAO_CONJUGE_IMPLAUSIVEL)
        ).extract(
            b"%PDF",
            mimetype="application/pdf",
            titular=TitularEsperado(nome="Carlos Eduardo Santos"),
        )
        assert out.data_casamento == date(2020, 6, 10)
        assert out.data_nascimento is None
        assert out.data_nascimento_confianca.value == "nenhuma"

    @pytest.mark.asyncio
    async def test_the_rejection_is_an_aviso_not_a_silent_drop(self) -> None:
        out = await LadderIdentityExtractor(
            ladder=_Ladder(CERTIDAO_CONJUGE_IMPLAUSIVEL)
        ).extract(
            b"%PDF",
            mimetype="application/pdf",
            titular=TitularEsperado(nome="Carlos Eduardo Santos"),
        )
        assert out.aviso is not None
        assert "data_nascimento_implausivel" in out.aviso
        assert "2006-05-10" in (out.aviso_mensagem or "")

    @pytest.mark.asyncio
    async def test_other_couple_level_facts_still_come_through(self) -> None:
        """The rejection is scoped to `data_nascimento` alone — the same
        posture `titulares_multiplos` already has for the couple-level
        facts on the same result."""
        out = await LadderIdentityExtractor(
            ladder=_Ladder(CERTIDAO_CONJUGE_IMPLAUSIVEL)
        ).extract(
            b"%PDF",
            mimetype="application/pdf",
            titular=TitularEsperado(nome="Carlos Eduardo Santos"),
        )
        assert out.estado_civil == "casado"
        assert out.regime_bens == "comunhao_parcial"
        assert out.data_casamento == date(2020, 6, 10)


class TestPlausibleSpouseBirthdateStillWrites:
    @pytest.mark.asyncio
    async def test_a_plausible_reading_is_unaffected(self) -> None:
        out = await LadderIdentityExtractor(
            ladder=_Ladder(CERTIDAO_CONJUGE_PLAUSIVEL)
        ).extract(
            b"%PDF",
            mimetype="application/pdf",
            titular=TitularEsperado(nome="Carlos Eduardo Santos"),
        )
        assert out.data_nascimento == date(1990, 5, 10)
        assert out.aviso is None


class TestNoDataCasamentoNoGuard:
    @pytest.mark.asyncio
    async def test_a_non_casamento_document_is_unaffected(self) -> None:
        """`data_casamento` is `None` on any document that is not a
        certidão de casamento — the guard is a no-op there by construction,
        never a false rejection on an unrelated document type."""
        texto = (
            "CARTEIRA NACIONAL DE HABILITACAO\n"
            "NOME\nJOAO DA SILVA\n"
            "DATA DE NASCIMENTO\n10/05/2006\n"
            "CPF\n111.222.333-44\n"
        )
        out = await LadderIdentityExtractor(ladder=_Ladder(texto)).extract(
            b"%PDF", mimetype="application/pdf"
        )
        assert out.data_casamento is None
        assert out.data_nascimento == date(2006, 5, 10)
        assert out.aviso is None
