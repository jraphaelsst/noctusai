"""Owner rule (2026-10-10): an inscrição that fails the município's mask is
NOT a reading — escalate once (stronger model), else drop it with a named
aviso. Never repair digits.

Live: a Cotia IPTU photo printed 18 digits (`23252-53-55-0304-00-000`) but
the vision transcription had 17 (`3253-53-55-0304-00-000`) and agreed with
itself, so text-anchoring alone passed it.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.imovel_hub import documentos_service as ds
from tests.modules.imovel_hub.conftest import (
    CODIGO, ORG_ID, documento_row, seed,
)
from tests.modules.imovel_hub.test_imovel_certidoes_estruturadas import (
    _analise_por_pagina, _paginas, _seed_storage,
)

IMPRESSA = "23252-53-55-0304-00-000"
ERRADA = "3253-53-55-0304-00-000"


def test_mascara_cotia():
    f = ds.inscricao_valida_na_mascara
    assert f(IMPRESSA, "Cotia") is True
    assert f(ERRADA, "Cotia") is False
    assert f(ERRADA, None, "PREFEITURA DE COTIA\nGUIA") is False  # city from the page
    assert f(ERRADA, None, "sem cidade") is None
    assert f("99.888.777-6", "Municipio Sem Perfil") is None


def _reler(chamadas, texto, via_visao=True):
    async def _fn(blob, mime, org):
        chamadas.append(1)
        return (ds.PaginaLida(texto=texto, via_visao=via_visao),)
    return _fn


async def _ler(scoped, fake_storage, *, analise, reler, municipio="Cotia", monkeypatch=None):
    did = str(uuid4())
    path = f"{ORG_ID}/imoveis/{CODIGO}/g"
    seed(scoped, documentos=[documento_row(did, tipo_documento="guia_iptu", storage_path=path)])
    await _seed_storage(fake_storage, path)
    monkeypatch.setattr(
        ds.dados_service, "municipio_do_imovel", lambda c, o, codigo: municipio
    )
    out = await ds.extrair_estrutura(
        scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
        extract_text=_paginas(("foto", True)),
        analyze_estrutura=analise,
        reler_texto=reler,
    )
    row = scoped.table("imovel_documentos").select("*").eq("id", did).execute().data[0]
    return out, row


def _conflitos(scoped):
    return scoped.table("imovel_campo_conflitos").select("*").execute().data


@pytest.mark.asyncio
async def test_17_digitos_nao_grava_escala_e_avisa(scoped, fake_storage, monkeypatch):
    chamadas = []
    # The stronger model still returns the wrong 17 digits.
    analise = _analise_por_pagina({
        "foto": {"inscricao_imobiliaria": ERRADA},
        f"INSCRICAO {ERRADA}": {"inscricao_imobiliaria": ERRADA},
    })
    out, row = await _ler(
        scoped, fake_storage, analise=analise,
        reler=_reler(chamadas, f"INSCRICAO {ERRADA}"), monkeypatch=monkeypatch,
    )
    assert chamadas == [1]
    assert row["inscricao_imobiliaria"] is None
    assert row["estrutura_erro"].startswith(ds.AVISO_INSCRICAO_ILEGIVEL)
    assert out["status"] == "sem_dados"
    assert _conflitos(scoped) == []
    assert ds._documento_out(row, {})["estrutura_aviso"]


@pytest.mark.asyncio
async def test_releitura_forte_corrige_e_grava(scoped, fake_storage, monkeypatch):
    chamadas = []
    analise = _analise_por_pagina({
        "foto": {"inscricao_imobiliaria": ERRADA},
        f"INSCRICAO CADASTRAL {IMPRESSA}": {"inscricao_imobiliaria": IMPRESSA},
    })
    out, row = await _ler(
        scoped, fake_storage, analise=analise,
        reler=_reler(chamadas, f"INSCRICAO CADASTRAL {IMPRESSA}"),
        monkeypatch=monkeypatch,
    )
    assert chamadas == [1]
    assert row["inscricao_imobiliaria"] == IMPRESSA
    assert row["estrutura_erro"] is None


@pytest.mark.asyncio
async def test_18_digitos_valido_nao_escala(scoped, fake_storage, monkeypatch):
    chamadas = []
    analise = _analise_por_pagina({"foto": {"inscricao_imobiliaria": IMPRESSA}})
    _, row = await _ler(
        scoped, fake_storage, analise=analise,
        reler=_reler(chamadas, "x"), monkeypatch=monkeypatch,
    )
    assert chamadas == []
    assert row["inscricao_imobiliaria"] == IMPRESSA


@pytest.mark.asyncio
async def test_municipio_desconhecido_comportamento_existente(scoped, fake_storage, monkeypatch):
    chamadas = []
    analise = _analise_por_pagina({"foto": {"inscricao_imobiliaria": ERRADA}})
    _, row = await _ler(
        scoped, fake_storage, analise=analise, municipio=None,
        reler=_reler(chamadas, "x"), monkeypatch=monkeypatch,
    )
    assert chamadas == []
    assert row["inscricao_imobiliaria"] == ERRADA
