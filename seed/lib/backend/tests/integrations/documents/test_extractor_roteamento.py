"""The PRODUCTION path of `LadderIdentityExtractor` (owner direction
2026-10-13): ONE read with the routed primary model; the trust gate
(`confianca`) judges every critical field; ONE fallback read only for a
doubtful critical field; agreement -> stored, disagreement -> empty + both
readings for review; no third read. Measurement mode keeps always-two-reads.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.factory import make_identity_extractor
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.releitura import AVISO_DIVERGENCIA
from noctusai_lib.integrations.documents.types import TextSource
from noctusai_lib.integrations.llm.usage import coletar_uso, record_usage

CPF_OK = "412.954.238-98"
CPF_OUTRO = "303.102.653-55"
CPF_DV_RUIM = "412.954.238-99"


def _cnh(cpf: str = CPF_OK, nome: str = "JOAO CARLOS PEREIRA") -> str:
    return f"NOME: {nome}\nCPF: {cpf}\nDATA DE NASCIMENTO: 12/05/1980\n"


class _Ladder:
    def __init__(self, *textos: str, erro=None):
        self.textos = list(textos)
        self.erro = erro
        self.chamadas: list[bool] = []

    async def to_text(self, content, mimetype=None, filename=None, *, pular_camada_texto=False):
        i = min(len(self.chamadas), len(self.textos) - 1)
        self.chamadas.append(pular_camada_texto)
        return (self.textos[i], TextSource.OCR, self.erro)


async def _ler(primaria: _Ladder, fallback: _Ladder, *, medicao=False, escalar=True, tipo="cnh", **kw):
    ex = LadderIdentityExtractor(
        ladder=primaria, escalation_ladder=fallback,
        escalar_releitura=escalar, modo_medicao=medicao,
    )
    return await ex.extract(b"x", mimetype="image/jpeg", filename="d.jpg", tipo_documento=tipo, **kw)


class TestOneReadWhenTheGatePasses:
    @pytest.mark.asyncio
    async def test_a_clean_document_costs_exactly_one_read(self):
        p, f = _Ladder(_cnh()), _Ladder(_cnh())
        out = await _ler(p, f)
        assert len(p.chamadas) == 1 and f.chamadas == []
        assert out.cpf == CPF_OK and out.nome == "JOAO CARLOS PEREIRA"
        assert out.divergencias == ()
        r = out.roteamento
        assert r.modo == "producao" and not r.fallback_executado
        assert (r.modelo_primario, r.modelo_fallback) == ("claude-sonnet-5", "claude-opus-5-5")
        assert {c.campo: c.resultado for c in r.campos}["cpf"] == "armazenado"


class TestOneFallbackReadForADoubtfulField:
    @pytest.mark.asyncio
    async def test_a_misread_cpf_triggers_one_fallback_read_that_stands_in(self):
        # The first read mis-copied the CPF (its check digit fails, so the
        # whole transcription fails its anchor); the fallback reads it right.
        p = _Ladder(_cnh(cpf=CPF_DV_RUIM))
        f = _Ladder(_cnh(cpf=CPF_OK))
        out = await _ler(p, f)
        assert len(f.chamadas) == 1, "exactly ONE fallback read, no third"
        assert out.roteamento.fallback_executado
        # The primary read failed its CPF anchor as a whole, so the fallback
        # read stands in where it passes the gate (its own DV verifies).
        assert out.cpf == CPF_OK

    @pytest.mark.asyncio
    async def test_agreement_on_a_doubtful_field_stores_it(self):
        texto = "NOME: JOAO CARLOS PEREIRA\nESTADO CIVIL: CASADO\n"
        p, f = _Ladder(texto), _Ladder(texto)
        ex = LadderIdentityExtractor(ladder=p, escalation_ladder=f, escalar_releitura=True)
        out = await ex.extract(
            b"x", mimetype="image/jpeg", filename="d.jpg", tipo_documento="cnh",
            confirmados={"nome": "MARIA DA SILVA SOUZA"},
        )
        # The cliente's confirmed name contradicts the read -> doubtful ->
        # one fallback read; both reads agree -> stored, marked concordou.
        assert len(f.chamadas) == 1
        desfecho = {c.campo: c for c in out.roteamento.campos}["nome"]
        assert desfecho.veredito == "duvidoso" and "diverge_de_valor_confirmado" in desfecho.motivos
        assert desfecho.acordo is True and desfecho.resultado == "concordou"
        assert out.nome == "JOAO CARLOS PEREIRA"

    @pytest.mark.asyncio
    async def test_disagreement_stores_nothing_and_sends_both_to_review(self):
        p = _Ladder("NOME: JOAO CARLOS PEREIRA\n")
        f = _Ladder("NOME: JOAO CARLOS PEREIRA FILHO\n")
        ex = LadderIdentityExtractor(ladder=p, escalation_ladder=f, escalar_releitura=True)
        out = await ex.extract(
            b"x", mimetype="image/jpeg", filename="d.jpg", tipo_documento="cnh",
            confirmados={"nome": "MARIA DA SILVA SOUZA"},
        )
        assert out.nome is None
        assert dict(out.divergencias)["nome"] == (
            "JOAO CARLOS PEREIRA", "JOAO CARLOS PEREIRA FILHO",
        )
        assert AVISO_DIVERGENCIA in (out.aviso or "")
        d = {c.campo: c for c in out.roteamento.campos}["nome"]
        assert d.resultado == "divergiu" and d.acordo is False
        assert d.impressao_primaria and d.impressao_fallback and d.impressao_primaria != d.impressao_fallback

    @pytest.mark.asyncio
    async def test_a_gate_passing_field_keeps_the_primary_value(self):
        # nome is doubtful (contradicts a confirmed value); cpf passes the
        # gate and must stand even though the fallback read another CPF.
        p = _Ladder(_cnh())
        f = _Ladder(_cnh(cpf=CPF_OUTRO, nome="JOAO CARLOS PEREIRA"))
        ex = LadderIdentityExtractor(ladder=p, escalation_ladder=f, escalar_releitura=True)
        out = await ex.extract(
            b"x", mimetype="image/jpeg", filename="d.jpg", tipo_documento="cnh",
            confirmados={"nome": "MARIA DA SILVA SOUZA"},
        )
        assert out.cpf == CPF_OK
        assert "cpf" not in dict(out.divergencias)

    @pytest.mark.asyncio
    async def test_a_failed_fallback_read_leaves_doubtful_fields_for_review(self):
        p = _Ladder("NOME: JOAO CARLOS PEREIRA\n")
        f = _Ladder("", erro=("timeout", "boom"))
        ex = LadderIdentityExtractor(ladder=p, escalation_ladder=f, escalar_releitura=True)
        out = await ex.extract(
            b"x", mimetype="image/jpeg", filename="d.jpg", tipo_documento="cnh",
            confirmados={"nome": "MARIA DA SILVA SOUZA"},
        )
        assert out.nome is None
        assert {c.campo: c.resultado for c in out.roteamento.campos}["nome"] == "nao_conciliado"


class TestModes:
    @pytest.mark.asyncio
    async def test_measurement_mode_keeps_always_two_reads(self):
        p, f = _Ladder(_cnh()), _Ladder(_cnh())
        out = await _ler(p, f, medicao=True)
        assert len(f.chamadas) >= 1, "measurement mode re-reads even a clean document"
        assert out.roteamento.modo == "medicao"

    @pytest.mark.asyncio
    async def test_the_per_org_off_switch_reads_once_and_reconciles_nothing(self):
        p, f = _Ladder(_cnh(cpf=CPF_DV_RUIM)), _Ladder(_cnh())
        out = await _ler(p, f, escalar=False)
        assert f.chamadas == []
        assert out.roteamento.modo == "leitura_unica"
        assert {c.campo: c.veredito for c in out.roteamento.campos}["cpf"] == "duvidoso"

    def test_the_factory_defaults_to_production(self):
        ex = make_identity_extractor(real=True)
        assert ex._escalar_releitura is True and ex._modo_medicao is False

    def test_the_primary_model_is_the_routed_one(self):
        ex = LadderIdentityExtractor()
        assert ex._modelos("cnh") == ("claude-sonnet-5", "claude-opus-5-5")
        assert LadderIdentityExtractor(provider="openai")._modelos("cnh")[0] == "gpt-4.1-mini"


class TestCostAttribution:
    @pytest.mark.asyncio
    async def test_coletar_uso_sees_every_event_of_its_scope(self):
        with coletar_uso() as fora:
            with coletar_uso() as dentro:
                await record_usage(
                    provider="anthropic", model="claude-sonnet-5", operation="vision",
                    prompt_tokens=1000, completion_tokens=100, total_tokens=1100,
                )
        assert len(dentro) == 1 and len(fora) == 1
        assert dentro[0].model == "claude-sonnet-5"


class _LadderComAvisos(_Ladder):
    """A ladder double with `ler` (the integration shape): every read
    carries the transcription's `avisos`."""

    def __init__(self, *textos: str, avisos: tuple[str, ...] = ()):
        super().__init__(*textos)
        self.avisos = avisos

    async def ler(self, content, mimetype=None, filename=None, *, pular_camada_texto=False):
        from noctusai_lib.integrations.documents.ladder import LeituraTexto

        texto, fonte, erro = await self.to_text(
            content, mimetype, filename, pular_camada_texto=pular_camada_texto
        )
        return LeituraTexto(texto, fonte, erro, self.avisos)


class TestReducedResolutionLowersTrust:
    @pytest.mark.asyncio
    async def test_a_reduced_resolution_primary_read_pays_one_fallback(self):
        from noctusai_lib.integrations.documents.vision_tiling import AVISO_RESOLUCAO_REDUZIDA

        p = _LadderComAvisos(_cnh(), avisos=(AVISO_RESOLUCAO_REDUZIDA,))
        f = _LadderComAvisos(_cnh())
        out = await _ler(p, f)
        assert len(f.chamadas) == 1
        nome = {c.campo: c for c in out.roteamento.campos}["nome"]
        assert nome.veredito == "duvidoso" and AVISO_RESOLUCAO_REDUZIDA in nome.motivos
        # The CPF's own check digit clears the soft doubt; nome agreed.
        assert out.cpf == CPF_OK and out.nome == "JOAO CARLOS PEREIRA"
        assert nome.resultado == "concordou"


class TestLaddersAreKeyedByModelAndPageClass:
    def test_routed_model_times_render_class(self):
        ex = LadderIdentityExtractor()
        card = ex._ladder_para("cnh")
        assert card is ex._ladder  # the routed default model on a card
        fb_card = ex._ladder_para("cnh", "claude-opus-5-5")
        pagina = ex._ladder_para("certidao_casamento")
        fb_pagina = ex._ladder_para("certidao_casamento", "claude-opus-5-5")
        assert len({id(card), id(fb_card), id(pagina), id(fb_pagina)}) == 4
        assert ex._get_escalation_ladder("certidao_casamento") is fb_pagina
