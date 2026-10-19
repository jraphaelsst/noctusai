"""FIXTURE ONLY: the CONTRACT §4.3 ``imob-lead`` v1 shape as test data.

The real v1 content is seeded later as DB data by the tech-lead; no runtime
module imports this file. Weights are illustrative (the owner edits them in the UI).
"""
from __future__ import annotations

from uuid import UUID

from app.qualificacao.models import (
    CriterioDef,
    EstagioDef,
    Opcao,
    ParametrosDef,
    VersaoPadrao,
)

VERSAO_ID = UUID("00000000-0000-0000-0000-0000000000a1")

_ordem = [0]


def _c(chave, grupo, tipo, pontuacao=None, opcoes=(), **kw):
    _ordem[0] += 10
    return CriterioDef(
        chave=chave, grupo=grupo, rotulo=chave.replace("_", " ").title(),
        descricao_modelo=f"como perguntar {chave}", tipo=tipo,
        opcoes=tuple(Opcao(o, o.title(), f"significa {o}", (f"sin_{o}",)) for o in opcoes),
        pontuacao=pontuacao or {}, ordem=_ordem[0], **kw,
    )


def _preenchido(k):
    return {"criterio": k, "op": "preenchido"}


def _em(k, *v):
    return {"criterio": k, "op": "em", "valores": list(v)}


PERFIL_BASICO = {"todos": [_preenchido("operacao"), _preenchido("tipo_imovel"),
                           _preenchido("faixa_preco"), _preenchido("regioes")]}
PRAZO_CURTO = _em("prazo_decisao", "imediato", "ate_3m", "3_6m")
PRAZO_LONGO = _em("prazo_decisao", "6_12m", "mais_12m", "indefinido")
FORMA_CONHECIDA = _em("forma_pagamento", "a_vista", "financiamento", "fgts", "permuta", "consorcio")
QUALIFICADO = {"todos": [PERFIL_BASICO, PRAZO_CURTO, FORMA_CONHECIDA]}


def versao_v1(**over) -> VersaoPadrao:
    _ordem[0] = 0
    criterios = (
        _c("operacao", "prontidao", "enum", {"opcoes": {"compra": 10, "aluguel": 10}}, ("compra", "aluguel")),
        _c("prazo_decisao", "prontidao", "enum",
           {"opcoes": {"imediato": 25, "ate_3m": 20, "3_6m": 12, "6_12m": 5, "mais_12m": 0, "indefinido": 0}},
           ("imediato", "ate_3m", "3_6m", "6_12m", "mais_12m", "indefinido")),
        _c("forma_pagamento", "prontidao", "enum",
           {"opcoes": {"a_vista": 15, "financiamento": 10, "fgts": 8, "permuta": 5, "consorcio": 4, "indefinido": 0}},
           ("a_vista", "financiamento", "fgts", "permuta", "consorcio", "indefinido")),
        _c("credito_aprovado", "prontidao", "enum", {"opcoes": {"sim": 10, "em_analise": 5}},
           ("sim", "nao", "em_analise", "nao_se_aplica")),
        _c("precisa_vender_atual", "bloqueios", "bool", {"true": -5, "false": 0}),
        _c("bloqueios", "bloqueios", "multi", {"por_item": -3},
           ("aprovacao_credito", "venda_imovel", "documentacao", "decisao_familiar", "mudanca_cidade", "outro")),
        _c("interesse_campanha", "interesse", "enum", {"opcoes": {"so_esse": 5, "esse_e_similares": 5, "aberto": 3}},
           ("so_esse", "esse_e_similares", "aberto", "nao_se_aplica")),
        _c("imoveis_gostou", "interesse", "numero", [{"min": 1, "pts": 10}]),
        _c("deseja_visitar", "interesse", "bool", {"true": 15, "false": 0}),
        _c("quer_mais_opcoes", "interesse", "bool", {"true": 3, "false": 0}),
        _c("tipo_imovel", "perfil_imovel", "enum", {"opcoes": {"casa": 5, "apartamento": 5, "terreno": 5, "comercial": 5}},
           ("casa", "apartamento", "terreno", "comercial")),
        _c("faixa_preco", "perfil_imovel", "faixa", [{"min": 0, "pts": 10}], sensivel="faixa", unidade="BRL"),
        _c("quartos_min", "perfil_imovel", "numero", [{"min": 1, "pts": 3}]),
        _c("vagas_min", "perfil_imovel", "numero", [{"min": 1, "pts": 2}]),
        _c("regioes", "perfil_imovel", "multi", {"preenchido": 8}),  # free values: org regions are org specs
        _c("caracteristicas", "perfil_imovel", "multi", {"por_item": 1, "max": 5},
           ("piscina", "churrasqueira", "jardim_quintal", "varanda", "elevador", "portaria", "area_lazer")),
        _c("animais", "perfil_vida", "bool"),
        _c("composicao_familiar", "perfil_vida", "texto", {"preenchido": 2}),
        _c("profissao", "perfil_vida", "texto", {"preenchido": 1}, sensivel="nao_coletar"),
        _c("trabalho_define_local", "perfil_vida", "bool"),
        _c("regiao_trabalho", "perfil_vida", "texto"),
        _c("proximidades", "perfil_vida", "multi", {}, ("comercio", "escolas", "rodovias", "transporte", "saude")),
        _c("nome", "contato", "texto", {"preenchido": 2}),
        _c("email", "contato", "texto", {"preenchido": 2}),
    )
    estagios = (
        EstagioDef("novo", "Novo", 0, {"todos": []}),
        EstagioDef("em_conversa", "Em conversa", 1,
                   {"algum": [_preenchido("operacao"), _preenchido("tipo_imovel"), _preenchido("interesse_campanha")]}),
        EstagioDef("perfil_basico", "Perfil basico", 2, PERFIL_BASICO),
        EstagioDef("qualificado_frio", "Qualificado frio", 3,
                   {"todos": [PERFIL_BASICO, {"algum": [PRAZO_LONGO, _preenchido("bloqueios")]}]}),
        EstagioDef("qualificado", "Qualificado", 4, QUALIFICADO),
        EstagioDef("pronto_para_corretor", "Pronto para corretor", 5,
                   {"todos": [QUALIFICADO, {"algum": [_preenchido("deseja_visitar"), _em("prazo_decisao", "imediato")]}]},
                   conclusivo=True),
        EstagioDef("descartado", "Descartado", 6, {"algum": []}, terminal=True),
    )
    parametros = ParametrosDef(
        minimo_para_ofertar={"todos": [
            _preenchido("operacao"),
            _em("interesse_campanha", "esse_e_similares", "aberto", "nao_se_aplica"),
            {"algum": [_preenchido("faixa_preco"), _preenchido("regioes")]},
        ]},
        lote_ofertas=3, score_max=100,
    )
    base = dict(
        id=VERSAO_ID, padrao_chave="imob-lead", versao=1, criterios=criterios, estagios=estagios,
        parametros=parametros, status="publicada",
    )
    base.update(over)
    return VersaoPadrao(**base)
