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
from noctusai_lib.integrations.documents.releitura import (
    AVISO_CAMPOS_NUCLEO_AUSENTES,
    AVISO_DIVERGENCIA,
    AVISO_RELEITURA,
)
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


class TestAlwaysEscalatesForCriticalFields:
    @pytest.mark.asyncio
    async def test_a_complete_clean_read_is_still_read_twice(self):
        """Owner decision 2026-10-13: the second read is the agreement gate's
        evidence, not a repair for a bad first read."""
        primeira = _Ladder(_RG_COMPLETO)
        escalada = _Ladder(_RG_COMPLETO)
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="rg")

        assert len(escalada.chamadas) == 1
        assert out.cpf == _CPF_VALIDO
        assert out.rg == "52.179.965-X"
        assert out.nome == "JOAO CARLOS PEREIRA"
        assert out.divergencias == ()
        assert out.leitura_comprometida is False
        assert out.rg_confianca == ExtractionConfidence.MEDIA  # promoted by agreement

    @pytest.mark.asyncio
    async def test_two_reads_that_disagree_store_nothing_and_say_so(self):
        outra = _RG_COMPLETO.replace("JOAO CARLOS PEREIRA", "JOAO CARLOS PEREIRO")
        out = await LadderIdentityExtractor(
            ladder=_Ladder(_RG_COMPLETO), escalar_releitura=True, escalation_ladder=_Ladder(outra),
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="rg")

        assert out.nome is None
        assert out.cpf == _CPF_VALIDO and out.rg == "52.179.965-X"  # the rest agree
        assert AVISO_DIVERGENCIA in out.aviso.split("+")
        assert {v for c, v in out.leituras_alternativas if c == "nome"} == {
            "JOAO CARLOS PEREIRA", "JOAO CARLOS PEREIRO",
        }

    @pytest.mark.asyncio
    async def test_a_failed_anchor_read_never_counts_toward_agreement(self):
        """A transcription whose CPF fails its check digit is `ancora_falhou`:
        a third read is taken and the two VALID ones agree around it."""
        ruim = _RG_COMPLETO.replace(_CPF_VALIDO, "412.954.238-99")
        primeira = _Ladder(ruim)
        escalada = _Ladder(_RG_COMPLETO)
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="rg")

        assert len(escalada.chamadas) == 2  # re-read + the extra read
        assert out.cpf == _CPF_VALIDO and out.nome == "JOAO CARLOS PEREIRA"
        assert out.divergencias == ()

    @pytest.mark.asyncio
    async def test_a_text_layer_read_is_exact_and_never_gated(self):
        primeira = _Ladder(_RG_COMPLETO, source=TextSource.TEXT_LAYER)
        escalada = _Ladder("NUNCA")
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="application/pdf", tipo_documento="rg")
        assert len(escalada.chamadas) == 0
        assert out.nome == "JOAO CARLOS PEREIRA" and out.divergencias == ()

    @pytest.mark.asyncio
    async def test_the_factory_default_escalates(self):
        from noctusai_lib.integrations.documents.factory import make_identity_extractor

        assert make_identity_extractor(real=True)._escalar_releitura is True
        assert make_identity_extractor(real=True, escalar_releitura=False)._escalar_releitura is False

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
        # The CPF is one read's only, but its check digit verifies: it stands.
        assert out.cpf == _CPF_VALIDO
        assert AVISO_RELEITURA in out.aviso.split("+")


class TestTriggerOnComprometida:
    @pytest.mark.asyncio
    async def test_clean_re_reads_that_agree_lift_the_comprometida_gate(self):
        primeira = _Ladder(_CNH_COMPROMETIDA)
        escalada = _Ladder(_RG_COMPLETO)
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="cnh")

        # the compromised read cannot count, so TWO clean re-reads are taken
        assert len(escalada.chamadas) == 2
        # The escalated read is clean — the brief's own condition ("if the
        # escalated read is not comprometida ... use it") lifts the gate a
        # human would otherwise have to clear by hand.
        assert out.leitura_comprometida is False
        assert AVISO_RELEITURA in out.aviso.split("+")
        assert out.cpf == _CPF_VALIDO and out.nome == "JOAO CARLOS PEREIRA"


class TestEscalatedAlsoComprometidaStaysWithheld:
    @pytest.mark.asyncio
    async def test_both_readings_recorded_still_withheld(self):
        primeira = _Ladder(_CNH_COMPROMETIDA)
        escalada = _Ladder(_CNH_COMPROMETIDA)
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="cnh")

        assert len(escalada.chamadas) == 2
        assert out.leitura_comprometida is True
        assert AVISO_RELEITURA in out.aviso.split("+")
        # no valid read -> nothing agrees, nothing is stored (not even the
        # check-digit-valid CPF: a compromised read never counts)
        assert out.nome is None and out.cpf is None
        assert "fora da concordância" in out.aviso_mensagem


class TestAgreementAndDisagreement:
    @pytest.mark.asyncio
    async def test_agreeing_cpf_is_applied_and_confidence_promoted(self):
        primeira = _Ladder(_RG_SEM_CPF)  # missing cpf -> triggers
        escalada = _Ladder(_RG_COMPLETO)
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="rg")
        assert out.cpf == _CPF_VALIDO
        # stands on its check digit alone (not an agreement): `cpf` is not
        # tempered by source, so a label-anchored, check-digit-verified read
        # is `alta` (see `real._ler`'s own comment on why CPF is exempt).
        assert out.cpf_confianca == ExtractionConfidence.ALTA
        assert out.nome == "JOAO CARLOS PEREIRA"  # both reads agree

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
        # the rg is only in ONE read: not corroborated -> no value
        assert out.rg is None
        # both cpf readings verify and they disagree: NO value, both attached
        assert out.cpf is None
        assert {v for c, v in out.leituras_alternativas if c == "cpf"} == {_CPF_VALIDO, outro_cpf_valido}
        assert out.nome == "JOAO CARLOS PEREIRA"
        assert AVISO_RELEITURA in out.aviso.split("+")
        assert AVISO_DIVERGENCIA in out.aviso.split("+")


#: The measured live-prod shape (2026-09-30): only nome + data_nascimento
#: ever come through, on EITHER read — no CPF/RG line at all, on a document
#: declared `tipo_documento="rg"`.
_RG_SO_NOME_E_DATA = (
    "NOME JOAO CARLOS PEREIRA\n"
    "DATA DE NASCIMENTO 12/05/1980\n"
)


class TestSilentPartialGuard:
    """🔴 Live prod, 2026-09-30: three `tipo_documento="rg"` uploads
    persisted `extracao_fonte="ocr"`, `data_nascimento_confianca="alta"` —
    CPF/RG/órgão/gênero/nacionalidade/filiação all NULL, `aviso` carrying
    `releitura_modelo_superior` (the escalation fired) but nothing saying
    the escalation did not actually help. `AVISO_CAMPOS_NUCLEO_AUSENTES` is
    the fix — see `real.py`'s own comment at the call site."""

    @pytest.mark.asyncio
    async def test_still_missing_core_fields_after_escalation_gets_its_own_aviso(self):
        primeira = _Ladder(_RG_SO_NOME_E_DATA)
        escalada = _Ladder(_RG_SO_NOME_E_DATA)  # stronger model, SAME gaps
        out = await LadderIdentityExtractor(
            ladder=primeira, escalar_releitura=True, escalation_ladder=escalada,
        ).extract(b"fake-bytes", mimetype="image/jpeg", tipo_documento="rg")

        assert len(escalada.chamadas) == 1  # escalation WAS tried
        assert out.cpf is None
        assert out.rg is None
        # What WAS found is never discarded by this guard.
        assert out.data_nascimento is not None
        assert out.data_nascimento_confianca == ExtractionConfidence.ALTA
        codigos = out.aviso.split("+")
        assert AVISO_CAMPOS_NUCLEO_AUSENTES in codigos
        assert "CPF" in out.aviso_mensagem
        assert "RG" in out.aviso_mensagem

    @pytest.mark.asyncio
    async def test_guard_applies_even_when_escalar_releitura_is_off(self):
        """Not gated on escalation running at all — a caller that never
        opts in (the class default) or a TEXT_LAYER read (which `deve_
        escalar` never re-reads) still needs to know its core fields never
        came through."""
        primeira = _Ladder(_RG_SO_NOME_E_DATA)
        out = await LadderIdentityExtractor(ladder=primeira).extract(
            b"fake-bytes", mimetype="image/jpeg", tipo_documento="rg"
        )
        assert AVISO_CAMPOS_NUCLEO_AUSENTES in out.aviso.split("+")

    @pytest.mark.asyncio
    async def test_a_complete_read_never_gets_the_guard(self):
        primeira = _Ladder(_RG_COMPLETO)
        out = await LadderIdentityExtractor(ladder=primeira).extract(
            b"fake-bytes", mimetype="image/jpeg", tipo_documento="rg"
        )
        assert (out.aviso or "") == "" or AVISO_CAMPOS_NUCLEO_AUSENTES not in out.aviso.split("+")

    @pytest.mark.asyncio
    async def test_no_tipo_documento_never_triggers_the_guard(self):
        """An undeclared type carries no known completeness contract — see
        `releitura.campos_nucleo_faltando`'s own docstring."""
        primeira = _Ladder(_RG_SO_NOME_E_DATA)
        out = await LadderIdentityExtractor(ladder=primeira).extract(
            b"fake-bytes", mimetype="image/jpeg"
        )
        assert (out.aviso or "") == "" or AVISO_CAMPOS_NUCLEO_AUSENTES not in out.aviso.split("+")
