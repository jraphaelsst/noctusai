"""Daily generation limits: the ONE resolver every cap site reads (geracao-contract.md §9.4.1).

Each limit is an integer per rolling 24 h. Resolution, first VALID answer wins:

1. ``public.org_settings (org_id, key=chave)`` -- this org's override (Configurações -> Limites diários);
2. ``public.platform_settings (key=chave)``     -- the NoctusAI-wide default;
3. env ``CHAVE``                                -- the deploy default;
4. ``cfg.<chave>``                              -- ``app/config.py`` (and the DI seam tests override).

Tiers 1-3 are the seed credential chain (``resolve_credential``: cached, a write in this process invalidates it). A
value is VALID when it is an integer in ``[1, maximo]``; anything else is skipped with a warning -- never a 500,
never "unlimited". ``maximo`` is a fixed constant (10 x the code default).

The write is ``social_wiring.cs_limite_geracao_definir`` (migration 361): the override and its event row in ONE
transaction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional

from noctusai_lib.config.credentials import invalidate_credential_cache, resolve_credential

logger = logging.getLogger(__name__)

#: The settings page section the 429s point to (FE route ``/configuracoes/limites``).
ROTA_LIMITES = "/configuracoes/limites"

RPC_DEFINIR = "cs_limite_geracao_definir"


@dataclass(frozen=True)
class LimiteSpec:
    chave: str
    rotulo: str
    descricao: str
    escopo: str  # "usuario" | "marca" | "org"
    padrao_codigo: int

    @property
    def maximo(self) -> int:
        return 10 * self.padrao_codigo


LIMITES: tuple[LimiteSpec, ...] = (
    LimiteSpec("headline_lotes_dia_usuario", "Gerações de headlines por pessoa",
               "Quantas vezes cada pessoa pode gerar headlines em 24 horas.", "usuario", 30),
    LimiteSpec("headlines_sugeridas_por_dia_marca", "Estruturas na sugestão automática diária, por marca",
               "Quantas estruturas a sugestão automática do dia usa por marca (2 headlines cada).", "marca", 5),
    LimiteSpec("roteiros_dia_usuario", "Roteiros por pessoa",
               "Quantos roteiros cada pessoa pode criar em 24 horas.", "usuario", 20),
    LimiteSpec("legendas_dia_usuario", "Legendas por pessoa",
               "Quantas legendas com IA cada pessoa pode gerar em 24 horas.", "usuario", 40),
    LimiteSpec("chat_mensagens_dia_usuario", "Mensagens no chat por pessoa",
               "Quantas mensagens cada pessoa pode enviar ao chat em 24 horas.", "usuario", 100),
    LimiteSpec("chat_mensagens_dia_org", "Mensagens no chat da organização (total)",
               "Quantas mensagens a organização inteira pode enviar ao chat em 24 horas.", "org", 400),
)
POR_CHAVE: dict[str, LimiteSpec] = {s.chave: s for s in LIMITES}
CHAVES: frozenset[str] = frozenset(POR_CHAVE)

Leitor = Callable[[str, Optional[str]], Optional[str]]


class LimiteInvalido(ValueError):
    """An unknown key or a value outside ``[1, maximo]`` (the API answers 422)."""


def _spec(chave: str) -> LimiteSpec:
    spec = POR_CHAVE.get(chave)
    if spec is None:
        raise LimiteInvalido(f"Limite desconhecido: {chave}")
    return spec


def _valido(spec: LimiteSpec, bruto: Any, origem: str) -> Optional[int]:
    """``bruto`` as a limit, or None (with a warning) when it is not an integer in ``[1, maximo]``."""
    if bruto is None or (isinstance(bruto, str) and not bruto.strip()):
        return None
    try:
        valor = int(str(bruto).strip())
    except ValueError:
        logger.warning("limites_geracao: %s=%r (%s) is not an integer; skipped", spec.chave, bruto, origem)
        return None
    if not 1 <= valor <= spec.maximo:
        logger.warning("limites_geracao: %s=%s (%s) outside [1, %s]; skipped", spec.chave, valor, origem, spec.maximo)
        return None
    return valor


def padrao_limite(chave: str, cfg: Any, *, ler: Leitor = resolve_credential) -> int:
    """What applies when the org has no override: platform_settings -> env -> ``cfg.<chave>`` -> code default."""
    spec = _spec(chave)
    valor = _valido(spec, ler(chave, None), "platform/env")
    if valor is not None:
        return valor
    return _valido(spec, getattr(cfg, chave, None), "config") or spec.padrao_codigo


def limite_geracao(chave: str, org_id: Optional[str], cfg: Any, *, ler: Leitor = resolve_credential) -> int:
    """The effective daily limit ``chave`` for ``org_id`` (see the module docstring for the precedence)."""
    spec = _spec(chave)
    if org_id:
        valor = _valido(spec, ler(chave, str(org_id)), "org")
        if valor is not None:
            return valor
    return padrao_limite(chave, cfg, ler=ler)


def limites_geracao(org_id: Optional[str], cfg: Any, *, ler: Leitor = resolve_credential) -> dict[str, int]:
    """All six effective limits for ``org_id``."""
    return {s.chave: limite_geracao(s.chave, org_id, cfg, ler=ler) for s in LIMITES}


def validar_alteracoes(alteracoes: Mapping[str, Optional[int]]) -> dict[str, Optional[int]]:
    """Every key known and every value an integer in ``[1, maximo]`` (or None = restore). Raises before ANY write."""
    if not alteracoes:
        raise LimiteInvalido("Informe ao menos um limite")
    saida: dict[str, Optional[int]] = {}
    for chave, valor in alteracoes.items():
        spec = _spec(chave)
        if valor is not None:
            if isinstance(valor, bool) or not isinstance(valor, int):
                raise LimiteInvalido(f"{spec.rotulo}: o valor deve ser um número inteiro")
            if not 1 <= valor <= spec.maximo:
                raise LimiteInvalido(f"{spec.rotulo}: o valor deve estar entre 1 e {spec.maximo}")
        saida[chave] = valor
    return saida


def listar(org_id: str, cfg: Any, *, ler_org: Leitor, ler: Leitor = resolve_credential) -> list[dict[str, Any]]:
    """The screen's rows: effective value, default, ceiling and whether this org has its own override.

    ``ler_org`` reads the org tier ONLY (the seed's ``resolve_org_credential``), so ``personalizado`` never
    mistakes a platform default for an override.
    """
    itens: list[dict[str, Any]] = []
    for spec in LIMITES:
        padrao = padrao_limite(spec.chave, cfg, ler=ler)
        proprio = _valido(spec, ler_org(spec.chave, str(org_id)), "org")
        itens.append({
            "chave": spec.chave, "rotulo": spec.rotulo, "descricao": spec.descricao, "escopo": spec.escopo,
            "valor": proprio if proprio is not None else padrao, "padrao": padrao, "maximo": spec.maximo,
            "personalizado": proprio is not None,
        })
    return itens


def definir(db: Any, org_id: str, alteracoes: Mapping[str, Optional[int]], ator_id: Optional[str]) -> list[dict]:
    """Apply validated changes, one RPC per key (each = override + event in one transaction). Returns the RPC answers."""
    validas = validar_alteracoes(alteracoes)
    respostas: list[dict] = []
    try:
        for chave, valor in validas.items():
            res = db.rpc(RPC_DEFINIR, {
                "p_org": str(org_id), "p_chave": chave, "p_valor": valor,
                "p_ator": str(ator_id) if ator_id else None,
            }).execute()
            respostas.append({"chave": chave, **(_primeira(res.data) or {})})
    finally:
        invalidate_credential_cache()  # this process serves the new limits at once (other workers within the TTL)
    return respostas


def _primeira(data: Any) -> Optional[dict]:
    if isinstance(data, dict):
        return data
    if isinstance(data, Iterable) and not isinstance(data, (str, bytes)):
        for item in data:
            return item if isinstance(item, dict) else None
    return None


__all__ = [
    "CHAVES", "LIMITES", "LimiteInvalido", "LimiteSpec", "POR_CHAVE", "ROTA_LIMITES", "RPC_DEFINIR",
    "definir", "limite_geracao", "limites_geracao", "listar", "padrao_limite", "validar_alteracoes",
]
