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
    CODIGO, ORG_ID, dados_row, documento_row, imovel_row, seed,
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


async def _ler(scoped, fake_storage, *, analise, reler, municipio="Cotia", dados=None):
    did = str(uuid4())
    path = f"{ORG_ID}/imoveis/{CODIGO}/g"
    # municipio_do_imovel runs for real, reading the imóvel's cidade (the
    # registry carries no snap_cidade, so a None município is truly unknown).
    seed(
        scoped,
        imoveis=[imovel_row(cidade=municipio)],
        dados=dados,
        documentos=[documento_row(did, tipo_documento="guia_iptu", storage_path=path)],
    )
    await _seed_storage(fake_storage, path)
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
async def test_17_digitos_nao_grava_escala_e_avisa(scoped, fake_storage):
    chamadas = []
    # The stronger model still returns the wrong 17 digits.
    analise = _analise_por_pagina({
        "foto": {"inscricao_imobiliaria": ERRADA},
        f"INSCRICAO {ERRADA}": {"inscricao_imobiliaria": ERRADA},
    })
    out, row = await _ler(
        scoped, fake_storage, analise=analise,
        reler=_reler(chamadas, f"INSCRICAO {ERRADA}"),
    )
    assert chamadas == [1]
    assert row["inscricao_imobiliaria"] is None
    assert row["estrutura_erro"].startswith(ds.AVISO_INSCRICAO_ILEGIVEL)
    assert out["status"] == "sem_dados"
    assert _conflitos(scoped) == []
    assert ds._documento_out(row, {})["estrutura_aviso"]


@pytest.mark.asyncio
async def test_releitura_forte_corrige_e_grava(scoped, fake_storage):
    chamadas = []
    analise = _analise_por_pagina({
        "foto": {"inscricao_imobiliaria": ERRADA},
        f"INSCRICAO CADASTRAL {IMPRESSA}": {"inscricao_imobiliaria": IMPRESSA},
    })
    out, row = await _ler(
        scoped, fake_storage, analise=analise,
        reler=_reler(chamadas, f"INSCRICAO CADASTRAL {IMPRESSA}"),
    )
    assert chamadas == [1]
    assert row["inscricao_imobiliaria"] == IMPRESSA
    assert row["estrutura_erro"] is None


@pytest.mark.asyncio
async def test_18_digitos_valido_nao_escala(scoped, fake_storage):
    chamadas = []
    analise = _analise_por_pagina({"foto": {"inscricao_imobiliaria": IMPRESSA}})
    _, row = await _ler(
        scoped, fake_storage, analise=analise,
        reler=_reler(chamadas, "x"),
    )
    assert chamadas == []
    assert row["inscricao_imobiliaria"] == IMPRESSA


@pytest.mark.asyncio
async def test_municipio_desconhecido_comportamento_existente(scoped, fake_storage):
    chamadas = []
    analise = _analise_por_pagina({"foto": {"inscricao_imobiliaria": ERRADA}})
    _, row = await _ler(
        scoped, fake_storage, analise=analise, municipio=None,
        reler=_reler(chamadas, "x"),
    )
    assert chamadas == []
    assert row["inscricao_imobiliaria"] == ERRADA


# ─── a photo that fits the mask but contradicts the CND on file ──────────
# Live 2026-10-12: the photo read 32252-… against the CND's printed 23252-…
# (two digits swapped — 18 digits, the mask is satisfied).
TROCADA = "32252-53-55-0304-00-000"
DA_CND = "23252.53.55.0304.00.000"


def _dados_da_cnd(origem="cnd_iptu"):
    return [dados_row(
        prefeitura_cadastro_imobiliario=DA_CND,
        prefeitura_cadastro_imobiliario_origem=origem,
        prefeitura_cadastro_imobiliario_documento_id=str(uuid4()),
    )]


@pytest.mark.asyncio
async def test_foto_que_diverge_da_cnd_escala_e_nao_grava(scoped, fake_storage):
    chamadas = []
    analise = _analise_por_pagina({
        "foto": {"inscricao_imobiliaria": TROCADA},
        f"INSCRICAO {TROCADA}": {"inscricao_imobiliaria": TROCADA},
    })
    out, row = await _ler(
        scoped, fake_storage, analise=analise, dados=_dados_da_cnd(),
        reler=_reler(chamadas, f"INSCRICAO {TROCADA}"),
    )
    assert chamadas == [1]
    assert row["inscricao_imobiliaria"] is None
    assert row["estrutura_erro"].startswith(ds.AVISO_INSCRICAO_DIVERGENTE)
    assert _conflitos(scoped) == []  # nothing for a human to adjudicate


@pytest.mark.asyncio
async def test_releitura_que_confere_com_a_cnd_grava(scoped, fake_storage):
    chamadas = []
    analise = _analise_por_pagina({
        "foto": {"inscricao_imobiliaria": TROCADA},
        f"INSCRICAO {IMPRESSA}": {"inscricao_imobiliaria": IMPRESSA},
    })
    _, row = await _ler(
        scoped, fake_storage, analise=analise, dados=_dados_da_cnd(),
        reler=_reler(chamadas, f"INSCRICAO {IMPRESSA}"),
    )
    assert chamadas == [1]
    assert row["inscricao_imobiliaria"] == IMPRESSA
    assert row["estrutura_erro"] is None


@pytest.mark.asyncio
async def test_foto_que_confere_com_a_cnd_nao_escala(scoped, fake_storage):
    chamadas = []
    analise = _analise_por_pagina({"foto": {"inscricao_imobiliaria": IMPRESSA}})
    _, row = await _ler(
        scoped, fake_storage, analise=analise, dados=_dados_da_cnd(),
        reler=_reler(chamadas, "x"),
    )
    assert chamadas == []
    assert row["inscricao_imobiliaria"] == IMPRESSA


@pytest.mark.asyncio
async def test_valor_da_matricula_nao_e_referencia(scoped, fake_storage):
    # Only a prefeitura document is exact enough to judge a photo by; a
    # matrícula-sourced value keeps the ordinary conflict path.
    chamadas = []
    analise = _analise_por_pagina({"foto": {"inscricao_imobiliaria": TROCADA}})
    _, row = await _ler(
        scoped, fake_storage, analise=analise, dados=_dados_da_cnd(origem="matricula"),
        reler=_reler(chamadas, "x"),
    )
    assert chamadas == []
    assert row["inscricao_imobiliaria"] == TROCADA
