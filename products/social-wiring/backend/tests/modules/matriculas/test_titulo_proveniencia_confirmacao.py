"""F72 — a título phrase accepted UNCHANGED is stored as extracted+confirmed
(`origem='matricula'` + `_confirmado_por/_em`), an EDITED one as operator-typed
(`manual`). Decided server-side against the current suggestion. All data
invented; only the layout mirrors a real matrícula."""
from __future__ import annotations

from uuid import UUID

from tests.modules.imovel_hub.conftest import dados_row
from tests.modules.matriculas.conftest import CODIGO, ORG_ID, extracao_row, registry_row, seed
from tests.modules.matriculas.test_predecessora_r5 import TEXTO

from app.modules.matriculas import estrutura_service as svc
from app.modules.matriculas import titulo_service

ORG = UUID(ORG_ID)


def _com_titulo(scoped):
    ext = extracao_row(texto=TEXTO)
    seed(scoped, registry=[registry_row()], extracoes=[ext])
    ato = next(a for a in svc.atos_da_extracao(scoped, ORG, ext) if a["kind"] == "R" and a["numero"] == 4)
    scoped.set_table_data("imovel_dados", [dados_row(
        titulo_aquisitivo_extracao_id=ext["id"], titulo_aquisitivo_ato_id=ato["id"],
        titulo_aquisitivo_char_inicio=int(ato["char_inicio"]),
        titulo_aquisitivo_char_fim=int(ato["char_fim"]),
        titulo_aquisitivo_origem="manual", titulo_aquisitivo_confirmado_por="u-1",
    )])


def _linha(scoped):
    return scoped.table("imovel_dados").select("*").execute().data[0]


def test_unchanged_suggestion_is_extracted_and_confirmed(client, scoped):
    _com_titulo(scoped)
    sugestao = titulo_service.obter_titulo(scoped, ORG, CODIGO)["sugestao"]
    assert sugestao

    out = titulo_service.confirmar_titulo(scoped, ORG, CODIGO, texto=sugestao, usuario_id="u-1")

    linha = _linha(scoped)
    assert linha["titulo_aquisitivo_texto_origem"] == "matricula"
    assert linha["titulo_aquisitivo_texto_confirmado_por"] == "u-1"
    assert linha["titulo_aquisitivo_texto_confirmado_em"]
    assert out["confirmado"]["origem"] == "matricula"


def test_rewrapped_whitespace_is_still_unchanged(client, scoped):
    _com_titulo(scoped)
    sugestao = titulo_service.obter_titulo(scoped, ORG, CODIGO)["sugestao"]

    titulo_service.confirmar_titulo(
        scoped, ORG, CODIGO, texto="  " + sugestao.replace(" ", "  ", 1) + "\n", usuario_id="u-1",
    )

    assert _linha(scoped)["titulo_aquisitivo_texto_origem"] == "matricula"


def test_edited_suggestion_is_manual(client, scoped):
    _com_titulo(scoped)
    sugestao = titulo_service.obter_titulo(scoped, ORG, CODIGO)["sugestao"]

    titulo_service.confirmar_titulo(scoped, ORG, CODIGO, texto=sugestao + " (retificado)", usuario_id="u-1")

    linha = _linha(scoped)
    assert linha["titulo_aquisitivo_texto_origem"] == "manual"
    assert linha["titulo_aquisitivo_texto_confirmado_por"] == "u-1"


def test_typed_text_with_no_suggestion_is_manual(client, scoped):
    seed(scoped, registry=[registry_row()], extracoes=[extracao_row(texto=TEXTO)])
    scoped.set_table_data("imovel_dados", [dados_row()])

    titulo_service.confirmar_titulo(scoped, ORG, CODIGO, texto="por escritura qualquer", usuario_id="u-1")

    assert _linha(scoped)["titulo_aquisitivo_texto_origem"] == "manual"
