"""The two structured-extraction calls of the channel API -- the episode summary and the transport decision.

Schemas in code, words in rows: the system prompts are the texts ``resumo.sistema`` / ``decisao.sistema``,
the labels ``resumo.rotulo_*`` / ``decisao.rotulo_*``, the tool descriptions the rows ``registrar_resumo`` /
``registrar_escolha`` of ``agent_version_ferramentas`` (CONTRACT §2.1 rows 14-15, D13).
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

from noctusai_lib.integrations.llm import ToolSpec

from app.channels.tool_registry import enriquecer_schema
from app.schemas.channels import DESFECHOS, DESFECHOS_BASE, DESFECHOS_VENDAS
from app.studio.models import ConteudoBundle

__all__ = [
    "DESFECHOS",
    "DESFECHOS_BASE",
    "DESFECHOS_LEGADO",
    "DESFECHOS_VENDAS",
    "DESFECHO_INVALIDOS",
    "desfechos_oferecidos",
    "rotulos_desfecho",
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
#: What a published version with NO ``desfecho_sugerido.<v>`` label offered before the outcomes became data.
DESFECHOS_LEGADO = ("qualificado", "frio", "captacao", "invalido", "em_andamento")
_PREFIXO_ROTULO = "desfecho_sugerido."
logger = logging.getLogger(__name__)
#: Out-of-set model outcomes seen (value -> count) since boot; each one is also logged.
DESFECHO_INVALIDOS: Counter[str] = Counter()
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


def rotulos_desfecho(parametros: Mapping[str, Any]) -> dict[str, str]:
    """The non-blank ``desfecho_sugerido.<valor>`` labels of a ``registrar_resumo`` row (value -> label)."""
    return {k[len(_PREFIXO_ROTULO):]: v for k, v in parametros.items()
            if k.startswith(_PREFIXO_ROTULO) and isinstance(v, str) and v.strip()}


def desfechos_oferecidos(c: ConteudoBundle) -> tuple[str, ...]:
    """The outcomes this agent offers = exactly the values labelled in its effective ``registrar_resumo`` row.
    A row with no label at all is a legacy published version: it keeps the 5 legacy values (explicit, logged)."""
    f = _linha(c, "registrar_resumo")
    rotulados = rotulos_desfecho(f.parametros)
    if not rotulados:
        logger.info("agents.extracao.desfecho.legado reason=sem_rotulos offered=%s", ",".join(DESFECHOS_LEGADO))
        return DESFECHOS_LEGADO
    return tuple(v for v in DESFECHOS if v in rotulados)


def resumo_tool(c: ConteudoBundle) -> ToolSpec:
    f = _linha(c, "registrar_resumo")
    oferecidos = desfechos_oferecidos(c)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "resumo": {"type": "string", "maxLength": RESUMO_MAX_CHARS},
            "desfecho_sugerido": {"type": "string", "enum": list(oferecidos)},
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


def shape_resumo(raw: Mapping[str, Any], oferecidos: tuple[str, ...] = DESFECHOS) -> dict[str, Any]:
    """The model's structured output, normalised. Unusable shape => ``ValueError`` (the route answers 502)."""
    resumo = raw.get("resumo")
    if not isinstance(resumo, str) or not resumo.strip():
        raise ValueError("resumo missing")
    resumo = " ".join(redigir_contatos(resumo).split())
    if len(resumo) > RESUMO_MAX_CHARS:
        resumo = resumo[: RESUMO_MAX_CHARS - 1].rstrip() + "…"
    desfecho = raw.get("desfecho_sugerido")
    if desfecho not in oferecidos:
        # Display-only value: the summary is still good, so it degrades to "em_andamento" -- loudly, never silently.
        DESFECHO_INVALIDOS[str(desfecho)] += 1
        logger.warning("agents.extracao.desfecho.invalido value=%r offered=%s", desfecho, ",".join(oferecidos))
        desfecho = "em_andamento"
    # NOC-REMEDIATE[desfecho-persistido]: record the outcome on the summary/handoff event; today it only rides the 200 body — 2026-11-10
    return {"resumo": resumo, "desfecho_sugerido": desfecho}


def montar_escolha_pedido(c: ConteudoBundle, regra: str, opcoes: list[str], dados: Mapping[str, Any]) -> tuple[str, str]:
    linhas = "\n".join(f"- {k}: {v}" for k, v in sorted(dados.items())) or _texto(c, "decisao.sem_dados")
    system = _texto(c, "decisao.sistema").replace("{regra}", regra)
    user = f"{_texto(c, 'decisao.rotulo_opcoes')} {', '.join(opcoes)}\n\n{_texto(c, 'decisao.rotulo_dados')}\n{linhas}"
    return system, user
