"""CENPROT reader — `app.modules.certidoes.cenprot`.

Every identifier here is SYNTHETIC: `123.456.789-09` is the canonical
documentation CPF (valid check digits, belongs to nobody); the protocolo is
a counting sequence. The PDF is generated — never a real screenshot.
"""
from __future__ import annotations

import io
import json
from datetime import date

import pytest

from app.modules.certidoes.cenprot import (
    PROMPT_DATA,
    PROMPT_PROTOCOLO,
    estruturar_cenprot,
)

CPF = "12345678909"
CNPJ = "11222333000181"
PROTOCOLO = "0123456789"
REF = date(2026, 6, 20)


def _pdf_com_captura() -> bytes:
    """A one-page PDF whose only content is one embedded raster — the shape
    of a screenshot pasted into a PDF."""
    import fitz
    from PIL import Image

    img = Image.new("RGB", (1200, 700), "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_image(fitz.Rect(40, 100, 800, 543), stream=buf.getvalue())
    return doc.tobytes()


PDF = _pdf_com_captura()


HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-5"


class _Leitor:
    """Fake vision: answers per prompt, in call order; records calls.

    `protocolos` answer the cheap model's protocol reads, `fortes` the
    escalated model's; `data` is one answer for every date read, or a list
    (one per date read, in order)."""

    def __init__(self, protocolos, data, fortes=()):
        self.protocolos = list(protocolos)
        self.fortes = list(fortes)
        self.data = data
        self.chamadas: list[tuple[int, str, str]] = []

    async def __call__(self, imagem: bytes, prompt: str, modelo: str) -> str:
        self.chamadas.append((len(imagem), prompt, modelo))
        if prompt == PROMPT_DATA:
            d = self.data.pop(0) if isinstance(self.data, list) else self.data
            if isinstance(d, Exception):
                raise d
            return json.dumps({"data": d})
        fila = self.protocolos if modelo == HAIKU else self.fortes
        r = fila.pop(0)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r)


def _leitura(protocolo=PROTOCOLO, documento="123.456.789-09"):
    return {"protocolo": protocolo, "documento": documento}


async def _rodar(leitor, *, provider="anthropic", tipo="cpf", documento=CPF,
                 referencia=REF, pdf=PDF):
    return await estruturar_cenprot(
        pdf, "CENPROT", None,
        provider=provider,
        tipo_documento_esperado=tipo,
        documento_esperado=documento,
        referencia=referencia,
        ler=leitor,
    )


class TestEstruturarCenprot:
    @pytest.mark.asyncio
    async def test_leituras_concordantes_gravam_numero_e_data(self):
        leitor = _Leitor([_leitura(), _leitura()], "17/06/2026")
        r = await _rodar(leitor)
        assert (r.numero, r.emitida_em, r.avisos) == (PROTOCOLO, "2026-06-17", ())

    @pytest.mark.asyncio
    async def test_tres_leituras_em_recortes_diferentes(self):
        leitor = _Leitor([_leitura(), _leitura()], "17/06/2026")
        await _rodar(leitor)
        prompts = [(p, m) for _, p, m in leitor.chamadas]
        assert prompts.count((PROMPT_PROTOCOLO, HAIKU)) == 2
        assert prompts.count((PROMPT_DATA, SONNET)) == 2
        assert len(prompts) == 4  # no escalation when the cheap reads agree
        for prompt in (PROMPT_PROTOCOLO, PROMPT_DATA):
            tamanhos = {n for n, p, _ in leitor.chamadas if p == prompt}
            assert len(tamanhos) == 2  # two DIFFERENT crops, never the same pixels

    @pytest.mark.asyncio
    async def test_protocolo_divergente_nao_grava_nada(self):
        leitor = _Leitor([_leitura(), _leitura("0123456780")], "17/06/2026")
        r = await _rodar(leitor)
        assert (r.numero, r.emitida_em) == (None, None)
        assert any("Protocolo da Consulta" in a for a in r.avisos)

    @pytest.mark.asyncio
    async def test_protocolo_com_digito_faltando_e_recusado(self):
        curto = "012345678"
        r = await _rodar(_Leitor([_leitura(curto), _leitura(curto)], "17/06/2026"))
        assert r.numero is None

    @pytest.mark.asyncio
    async def test_documento_de_outra_pessoa_bloqueia_tudo(self):
        r = await _rodar(_Leitor([_leitura(), _leitura()], "17/06/2026"),
                         documento="52998224725")
        assert (r.numero, r.emitida_em) == (None, None)
        assert any("Documento Pesquisado" in a for a in r.avisos)

    @pytest.mark.asyncio
    async def test_digito_verificador_invalido_bloqueia_tudo(self):
        ruim = _leitura(documento="123.456.789-00")
        r = await _rodar(_Leitor([ruim, ruim], "17/06/2026"), documento=None)
        assert r.numero is None

    @pytest.mark.asyncio
    async def test_um_recorte_com_documento_valido_basta(self):
        r = await _rodar(_Leitor([_leitura(), _leitura(documento=None)], "17/06/2026"))
        assert r.numero == PROTOCOLO

    @pytest.mark.asyncio
    async def test_cnpj_valida_contra_cnpj(self):
        pj = _leitura(documento="11.222.333/0001-81")
        r = await _rodar(_Leitor([pj, pj], "17/06/2026"), tipo="cnpj", documento=CNPJ)
        assert r.numero == PROTOCOLO

    @pytest.mark.asyncio
    async def test_sem_documento_esperado_aceita_digito_verificador(self):
        r = await _rodar(_Leitor([_leitura(), _leitura()], "17/06/2026"),
                         tipo=None, documento=None)
        assert r.numero == PROTOCOLO

    @pytest.mark.parametrize("lida", ["17/06/2025", "17/06/2024", "17/12/2026"])
    @pytest.mark.asyncio
    async def test_data_fora_da_janela_nao_e_gravada(self, lida):
        # The measured failure: the year read 1+ years early.
        r = await _rodar(_Leitor([_leitura(), _leitura()], lida))
        assert r.numero == PROTOCOLO
        assert r.emitida_em is None
        assert any("janela" in a for a in r.avisos)

    @pytest.mark.parametrize("lida", ["31/02/2026", None, "2026-06-17", "ilegível"])
    @pytest.mark.asyncio
    async def test_data_invalida_nao_e_gravada(self, lida):
        r = await _rodar(_Leitor([_leitura(), _leitura()], lida))
        assert (r.numero, r.emitida_em) == (PROTOCOLO, None)

    @pytest.mark.asyncio
    async def test_sem_referencia_nao_grava_data(self):
        r = await _rodar(_Leitor([_leitura(), _leitura()], "17/06/2026"), referencia=None)
        assert (r.numero, r.emitida_em) == (PROTOCOLO, None)

    @pytest.mark.asyncio
    async def test_provedor_nao_medido_nao_le(self):
        leitor = _Leitor([], "17/06/2026")
        r = await _rodar(leitor, provider="openai")
        assert (r.numero, r.emitida_em) == (None, None)
        assert leitor.chamadas == []  # no spend on an unmeasured path

    @pytest.mark.asyncio
    async def test_pdf_sem_captura_le_a_pagina_e_sem_rotulo_nao_grava(self):
        # No landscape screenshot ⇒ the printed-page layout path: the page
        # itself is read; a page without the label yields nothing.
        import fitz

        doc = fitz.open()
        doc.new_page()
        nada = {"protocolo": None, "documento": None}
        leitor = _Leitor([nada, nada], "17/06/2026", fortes=[nada, nada])
        r = await _rodar(leitor, pdf=doc.tobytes())
        assert (r.numero, r.emitida_em) == (None, None)
        assert all(p == PROMPT_PROTOCOLO for _, p, _ in leitor.chamadas)

    @pytest.mark.asyncio
    async def test_falhas_de_leitura_nao_levantam(self):
        leitor = _Leitor([RuntimeError("quota"), "não é json"], RuntimeError("x"))
        r = await _rodar(leitor)
        assert (r.numero, r.emitida_em) == (None, None)
        assert r.avisos

    @pytest.mark.asyncio
    async def test_resposta_com_cerca_markdown(self):
        cerca = "```json\n" + json.dumps(_leitura()) + "\n```"
        r = await _rodar(_Leitor([cerca, cerca], "17/06/2026"))
        assert r.numero == PROTOCOLO

    @pytest.mark.asyncio
    async def test_avisos_nunca_carregam_o_valor_extraido(self):
        # 🔴 PRIVACY: diagnostics only.
        casos = [
            await _rodar(_Leitor([_leitura(), _leitura("0123456780")], "17/06/2026")),
            await _rodar(_Leitor([_leitura(), _leitura()], "17/06/2026"), documento="52998224725"),
            await _rodar(_Leitor([_leitura(), _leitura()], "17/06/2024")),
        ]
        for r in casos:
            for aviso in r.avisos:
                for valor in (CPF, "123.456.789-09", PROTOCOLO, "0123456780",
                              "17/06/2026", "17/06/2024", "52998224725"):
                    assert valor not in aviso


def _pdf_impresso() -> bytes:
    """The printed-page layout: the browser's print-to-PDF of the result —
    portrait page, no landscape screenshot, no taskbar."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((40, 120), "Protocolo da Consulta: (sintetico)")
    return doc.tobytes()


class TestEscalonamento:
    """Rung 2: the stronger model reads the same two crops only when the
    cheap reads did not self-validate — and must agree with itself."""

    @pytest.mark.asyncio
    async def test_divergencia_barata_escalona_e_forte_concordante_grava(self):
        leitor = _Leitor(
            [_leitura(), _leitura("012345678")], "17/06/2026",
            fortes=[_leitura(), _leitura()],
        )
        r = await _rodar(leitor)
        assert (r.numero, r.emitida_em) == (PROTOCOLO, "2026-06-17")
        modelos = [m for _, p, m in leitor.chamadas if p == PROMPT_PROTOCOLO]
        assert modelos.count(SONNET) == 2

    @pytest.mark.asyncio
    async def test_forte_discordante_de_si_mesmo_nao_grava(self):
        leitor = _Leitor(
            [_leitura(), _leitura("0123456780")], "17/06/2026",
            fortes=[_leitura(), _leitura("0123456781")],
        )
        r = await _rodar(leitor)
        assert (r.numero, r.emitida_em) == (None, None)

    @pytest.mark.asyncio
    async def test_identidade_ilegivel_escalona_e_forte_le_documento(self):
        ruim = _leitura(documento="123.456.789-00")
        leitor = _Leitor([ruim, ruim], "17/06/2026", fortes=[_leitura(), _leitura()])
        r = await _rodar(leitor, documento=None)
        assert r.numero == PROTOCOLO

    @pytest.mark.asyncio
    async def test_barato_e_forte_concordam_em_numeros_diferentes_nao_grava(self):
        # Each model agrees with itself on a DIFFERENT number: no winner.
        ruim = _leitura(documento="123.456.789-00")
        leitor = _Leitor(
            [ruim, ruim], "17/06/2026",
            fortes=[_leitura("0123456780"), _leitura("0123456780")],
        )
        r = await _rodar(leitor)
        assert r.numero is None
        assert any("Protocolo da Consulta" in a for a in r.avisos)


class TestData:
    @pytest.mark.asyncio
    async def test_duas_leituras_da_data_discordantes_nao_gravam(self):
        r = await _rodar(_Leitor([_leitura(), _leitura()], ["17/06/2026", "16/06/2026"]))
        assert (r.numero, r.emitida_em) == (PROTOCOLO, None)
        assert any("não concordaram" in a for a in r.avisos)

    @pytest.mark.asyncio
    async def test_digito_cortado_marcado_com_interrogacao_nao_e_completado(self):
        r = await _rodar(_Leitor([_leitura(), _leitura()], "17/06/202?"))
        assert (r.numero, r.emitida_em) == (PROTOCOLO, None)


class TestPaginaImpressa:
    @pytest.mark.asyncio
    async def test_pagina_impressa_le_o_topo_da_pagina_e_nao_le_data(self):
        leitor = _Leitor([_leitura(), _leitura()], "17/06/2026")
        r = await _rodar(leitor, pdf=_pdf_impresso())
        assert r.numero == PROTOCOLO
        assert r.emitida_em is None
        assert any("página impressa" in a for a in r.avisos)
        assert all(p == PROMPT_PROTOCOLO for _, p, _ in leitor.chamadas)
