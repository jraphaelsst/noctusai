"""`LadderIdentityExtractor` wires `releitura.deve_escalar` / `releitura.
mesclar` into its own `.extract()` — end to end, through the REAL two-ladder
mechanism (`ladder=` for the first read, `escalation_ladder=` for the
escalated re-read), not just the pure units (see `test_releitura.py`).

`escalar_releitura` defaults to `False` on `LadderIdentityExtractor` itself
(Fake-by-default posture — see `real.py`'s own comment); every test below
passes `escalar_releitura=True` explicitly to exercise the feature.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.releitura import AVISO_RELEITURA
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource

_CPF_VALIDO = "412.954.238-98"

#: A complete RG read: nome + cpf + rg all label-anchored — nothing for
#: `deve_escalar`'s trigger table to catch, and not comprometida.
_RG_COMPLETO = (
    "REGISTRO GERAL 52.179.965-X\n"
    "NOME JOAO CARLOS PEREIRA\n"
    "DATA DE NASCIMENTO 12/05/1980\n"
    f"CPF {_CPF_VALIDO}\n"
)

#: The same RG, missing its `CPF` line entirely — a genuinely incomplete
#: card read (nome + rg only).
_RG_SEM_CPF = (
    "REGISTRO GERAL 52.179.965-X\n"
    "NOME JOAO CARLOS PEREIRA\n"
    "DATA DE NASCIMENTO 12/05/1980\n"
)

#: The measured CNH-screenshot hallucination (`legibilidade.py`'s own
#: module docstring) — comprometida regardless of which fields it fills.
_CNH_COMPROMETIDA = (
    "CNH DIGITAL\n"
    "NOME: MARIA APARECIDA DAS DORES\n"
    "DATA DE NASCIMENTO: BRASILEROCA\n"
    f"CPF: {_CPF_VALIDO}\n"
    "CEP: 99 de abril\n"
    "FILIACAO: JOSE DA SILVA E MARIA APARECIDA DAS DORES\n"
)


class _Ladder:
    """DI stand-in for `DocumentTextLadder` — ONE canned read, no internal
    rung-switching (that mechanism has its own tests). `chamadas` records
    every `pular_camada_texto` this instance received — the call-COUNT
    assertion the brief asks for ("no trigger on a complete clean read: no
    second call")."""

    def __init__(self, texto: str, source: TextSource = TextSource.OCR, erro=None):
        self.texto = texto
        self.source = source
        self.erro = erro
        self.chamadas: list[bool] = []

    async def to_text(self, content, mimetype=None, filename=None, *, pular_camada_texto=False):
        self.chamadas.append(pular_camada_texto)
        return (self.texto, self.source, self.erro)


class TestNoTriggerOnCompleteCleanRead:
    @pytest.mark.asyncio
    async def test_escalation_ladder_is_never_called(self):
        primeira = _Ladder(_RG_COMPLETO)
        escalada = _Ladder("NUNCA DEVERIA SER LIDO")
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="rg")

        assert out.persistable_nome is False  # vision-sourced, tempered — unrelated to this test
        assert out.cpf == _CPF_VALIDO
        assert out.rg == "52.179.965-X"
        assert out.leitura_comprometida is False
        assert len(escalada.chamadas) == 0
        assert (out.aviso or "") == "" or AVISO_RELEITURA not in out.aviso.split("+")

    @pytest.mark.asyncio
    async def test_escalar_releitura_off_never_calls_escalation_ladder_even_when_incomplete(self):
        """The raw class default (`escalar_releitura=False`) — a caller
        that does not opt in never pays for the second call, even on a
        document that WOULD have triggered it."""
        primeira = _Ladder(_RG_SEM_CPF)
        escalada = _Ladder("NUNCA DEVERIA SER LIDO")
        out = await LadderIdentityExtractor(
            ladder=primeira, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="rg")

        assert out.cpf is None
        assert len(escalada.chamadas) == 0


class TestTriggerOnMissingCoreField:
    @pytest.mark.asyncio
    async def test_escalation_fills_the_missing_cpf(self):
        primeira = _Ladder(_RG_SEM_CPF)
        escalada = _Ladder(_RG_COMPLETO)
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="rg")

        assert len(escalada.chamadas) == 1
        assert escalada.chamadas == [True]  # straight to vision, no text-layer retry
        assert out.cpf == _CPF_VALIDO
        assert AVISO_RELEITURA in out.aviso.split("+")
        assert "preencheu" in out.aviso_mensagem


class TestTriggerOnComprometida:
    @pytest.mark.asyncio
    async def test_a_clean_escalated_read_lifts_the_comprometida_gate(self):
        primeira = _Ladder(_CNH_COMPROMETIDA)
        escalada = _Ladder(_RG_COMPLETO)
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="cnh")

        assert len(escalada.chamadas) == 1
        # The escalated read is clean — the brief's own condition ("if the
        # escalated read is not comprometida ... use it") lifts the gate a
        # human would otherwise have to clear by hand.
        assert out.leitura_comprometida is False
        assert AVISO_RELEITURA in out.aviso.split("+")
        assert out.cpf == _CPF_VALIDO  # both readings agree on the CPF


class TestEscalatedAlsoComprometidaStaysWithheld:
    @pytest.mark.asyncio
    async def test_both_readings_recorded_still_withheld(self):
        primeira = _Ladder(_CNH_COMPROMETIDA)
        escalada = _Ladder(_CNH_COMPROMETIDA)
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="cnh")

        assert len(escalada.chamadas) == 1
        assert out.leitura_comprometida is True
        assert AVISO_RELEITURA in out.aviso.split("+")
        motivos = out.aviso_mensagem.replace("é", "e")
        assert "tambem comprometida" in motivos


class TestAgreementAndDisagreement:
    @pytest.mark.asyncio
    async def test_agreeing_cpf_is_applied_and_confidence_promoted(self):
        primeira = _Ladder(_RG_SEM_CPF)  # missing cpf -> triggers
        escalada = _Ladder(_RG_COMPLETO)
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="rg")
        assert out.cpf == _CPF_VALIDO
        # FILLED verbatim from the escalated read (a gap, not an agreement)
        # — `cpf` is not tempered by source, so a label-anchored, check-
        # digit-verified read is `alta` regardless of which rung produced
        # the text (see `real._ler`'s own comment on why CPF is exempt).
        assert out.cpf_confianca == ExtractionConfidence.ALTA

    @pytest.mark.asyncio
    async def test_disagreeing_field_is_reported_absent_never_guessed(self):
        outro_cpf_valido = "111.444.777-35"
        # `cnh` requires nome+cpf+rg (see `releitura._TABELA_NUCLEO`) — the
        # first read carries nome+cpf but NO `rg` line at all, which is
        # enough on its own to trigger. The escalated read fills `rg` (a
        # gap) AND carries a DIFFERENT `cpf` (a genuine disagreement on a
        # field BOTH reads have) — proving the two are handled
        # independently in the same merge.
        primeira = _Ladder(
            "NOME JOAO CARLOS PEREIRA\n"
            f"CPF {_CPF_VALIDO}\n"
        )
        escalada = _Ladder(
            "REGISTRO GERAL 52.179.965-X\n"
            "NOME JOAO CARLOS PEREIRA\n"
            f"CPF {outro_cpf_valido}\n"
        )
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="cnh")

        assert len(escalada.chamadas) == 1
        assert out.rg == "52.179.965-X"  # the gap — filled
        assert out.cpf is None  # both reads had a value, and they disagree
        assert out.cpf_confianca == ExtractionConfidence.NENHUMA
        assert AVISO_RELEITURA in out.aviso.split("+")
        assert "divergiu" in out.aviso_mensagem
        assert "preencheu" in out.aviso_mensagem
