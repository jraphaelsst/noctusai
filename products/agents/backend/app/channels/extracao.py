"""The two structured-extraction calls of the channel API -- the episode summary and the transport decision.

Schemas in code, words in rows: the system prompts are the texts ``resumo.sistema`` / ``decisao.sistema``,
the labels ``resumo.rotulo_*`` / ``decisao.rotulo_*``, the tool descriptions the rows ``registrar_resumo`` /
``registrar_escolha`` of ``agent_version_ferramentas`` (CONTRACT §2.1 rows 14-15, D13).
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from noctusai_lib.integrations.llm import ToolSpec

from app.channels.tool_registry import enriquecer_schema
from app.studio.models import ConteudoBundle

__all__ = [
    "DESFECHOS",
    "ESCOLHA_MOTIVO_MAX",
    "RESUMO_MAX_CHARS",
    "ConteudoIncompleto",
    "escolha_tool",
    "montar_resumo_pedido",
    "montar_escolha_pedido",
    "redigir_contatos",
    "resumo_tool",
    "shape_resumo",
]

RESUMO_MAX_CHARS = 1200
ESCOLHA_MOTIVO_MAX = 200
DESFECHOS = ("qualificado", "frio", "captacao", "invalido", "em_andamento")
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_PHONE = re.compile(r"(?<![\w])\+?\d[\d\s().-]{6,}\d(?![\w])")
#: The one structural placeholder an extraction text may carry for a removed contact. Not prose.
_REMOVIDO = "[…]"


class ConteudoIncompleto(Exception):
    """A text / tool row the extraction needs is blank (the route answers 409 ``conteudo_incompleto``)."""


def _texto(c: ConteudoBundle, chave: str) -> str:
    t = c.texto(chave).strip()
    if not t:
        raise ConteudoIncompleto(chave)
    return t


def _linha(c: ConteudoBundle, nome: str) -> Any:
    for f in c.ferramentas:
        if f.ferramenta == nome and f.ativo and (f.descricao or "").strip():
            return f
    raise ConteudoIncompleto(f"ferramenta.{nome}")


def redigir_contatos(text: str) -> str:
    return _PHONE.sub(_REMOVIDO, _EMAIL.sub(_REMOVIDO, text))


def resumo_tool(c: ConteudoBundle) -> ToolSpec:
    f = _linha(c, "registrar_resumo")
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "resumo": {"type": "string", "maxLength": RESUMO_MAX_CHARS},
            "desfecho_sugerido": {"type": "string", "enum": list(DESFECHOS)},
        },
        "required": ["resumo", "desfecho_sugerido"],
        "additionalProperties": False,
    }
    enriquecer_schema(schema, f.parametros)
    return ToolSpec(name="registrar_resumo", description=f.descricao.strip(), parameters=schema)


def escolha_tool(c: ConteudoBundle, opcoes: list[str]) -> ToolSpec:
    f = _linha(c, "registrar_escolha")
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "escolha": {"type": "string", "enum": list(opcoes)},
            "motivo": {"type": "string", "maxLength": ESCOLHA_MOTIVO_MAX},
        },
        "required": ["escolha", "motivo"],
        "additionalProperties": False,
    }
    enriquecer_schema(schema, f.parametros)
    return ToolSpec(name="registrar_escolha", description=f.descricao.strip(), parameters=schema)


def montar_resumo_pedido(c: ConteudoBundle, registros: list[Any], desde: Any) -> tuple[str, str]:
    """``(system, user)`` of the summary call. The transcript is lead DATA: it never becomes an instruction."""
    cli, atd = _texto(c, "resumo.rotulo_cliente"), _texto(c, "resumo.rotulo_atendente")
    linhas: list[str] = []
    for r in registros:
        if desde is not None and r.created_at < desde:
            continue
        if r.role == "user" and r.texto:
            linhas.append(f"{cli} {r.texto}")
        elif r.role in ("assistant", "humano") and r.texto and r.texto.strip():
            linhas.append(f"{atd} {r.texto}")
    corpo = "\n".join(linhas) or _texto(c, "resumo.sem_mensagens")
    return _texto(c, "resumo.sistema"), f"{_texto(c, 'resumo.rotulo_conversa')}\n{corpo}"


def shape_resumo(raw: Mapping[str, Any]) -> dict[str, Any]:
    """The model's structured output, normalised. Unusable shape => ``ValueError`` (the route answers 502)."""
    resumo = raw.get("resumo")
    if not isinstance(resumo, str) or not resumo.strip():
        raise ValueError("resumo missing")
    resumo = " ".join(redigir_contatos(resumo).split())
    if len(resumo) > RESUMO_MAX_CHARS:
        resumo = resumo[: RESUMO_MAX_CHARS - 1].rstrip() + "…"
    desfecho = raw.get("desfecho_sugerido")
    return {"resumo": resumo, "desfecho_sugerido": desfecho if desfecho in DESFECHOS else "em_andamento"}


def montar_escolha_pedido(c: ConteudoBundle, regra: str, opcoes: list[str], dados: Mapping[str, Any]) -> tuple[str, str]:
    linhas = "\n".join(f"- {k}: {v}" for k, v in sorted(dados.items())) or _texto(c, "decisao.sem_dados")
    system = _texto(c, "decisao.sistema").replace("{regra}", regra)
    user = f"{_texto(c, 'decisao.rotulo_opcoes')} {', '.join(opcoes)}\n\n{_texto(c, 'decisao.rotulo_dados')}\n{linhas}"
    return system, user
