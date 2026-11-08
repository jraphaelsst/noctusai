"""Value types + errors of the platform prompt registry (``public.plataforma_agentes``, core migration 111)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Optional
from uuid import UUID

#: capacidade -> the model-catalog ``kind`` its model must belong to.
KIND_POR_CAPACIDADE = {"chat": "chat", "vision": "vision", "transcription": "audio"}

import re

#: Stable logical id: dotted lowercase segments (``agents.eval_improver``). Never a product slug or code path.
CHAVE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
CHAVE_MAX = 64


def chave_valida(chave: str) -> bool:
    return len(chave) <= CHAVE_MAX and bool(CHAVE_RE.match(chave))


__all__ = [
    "CHAVE_RE",
    "chave_valida",
    "KIND_POR_CAPACIDADE",
    "ChamadaMedida",
    "ChaveNaoEncontrada",
    "PromptEntry",
    "RegistroIAIndisponivel",
    "calcular_estatisticas",
]

#: Most recent measured calls per chave the aggregate reads.
ESTATISTICAS_JANELA = 1000


class RegistroIAIndisponivel(RuntimeError):
    """The registry row is missing, inactive, unreadable or no registry is configured. Never swallowed: the caller
    must not run the AI call (no baked-in fallback prompt exists, by design)."""


class ChaveNaoEncontrada(KeyError):
    """No registry row has that key (store-level; :func:`prompt_e_modelo` turns it into RegistroIAIndisponivel)."""


@dataclass(frozen=True)
class PromptEntry:
    chave: str
    nome: str
    descricao: str
    vendor: str
    modelo: str
    prompt: str
    ativo: bool = True
    capacidade: str = "chat"
    atualizado_em: Optional[datetime] = None
    atualizado_por: Optional[UUID] = None


@dataclass(frozen=True)
class ChamadaMedida:
    """One measured call. Counts, cost, latency, outcome -- never prompt or response text."""

    chave: str
    vendor: str
    modelo: str
    latencia_ms: int
    ok: bool
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None
    custo_usd: Optional[float] = None
    erro: Optional[str] = None
    capacidade: str = "chat"


def calcular_estatisticas(chamadas: list[dict]) -> list[dict]:
    """Per vendor+modelo: ``n``, ``p50_latencia_ms``, ``custo_medio_usd`` (mean over the calls that have a cost; ``None``
    when none does -- unmeasured, not zero), ``taxa_erro``."""
    grupos: dict[tuple[str, str], list[dict]] = {}
    for c in chamadas:
        grupos.setdefault((c["vendor"], c["modelo"]), []).append(c)
    out = []
    for (vendor, modelo), cs in sorted(grupos.items()):
        custos = [float(c["custo_usd"]) for c in cs if c.get("custo_usd") is not None]
        out.append({
            "vendor": vendor, "modelo": modelo, "n": len(cs),
            "p50_latencia_ms": int(median(c["latencia_ms"] for c in cs)),
            "custo_medio_usd": (sum(custos) / len(custos)) if custos else None,
            "taxa_erro": sum(1 for c in cs if not c["ok"]) / len(cs),
        })
    return out
