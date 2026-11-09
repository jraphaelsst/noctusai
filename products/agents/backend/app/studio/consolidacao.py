"""Eval-case consolidation: the pure state machine (owner rule 2026-11-09). No IO.

Per (case, agent) a case is ``em_validacao`` (counting consecutive correct passes), ``consolidado`` (proved; NOT re-run
while nothing it depends on changes) or ``revalidar`` (a change affected it; a shorter streak brings it back).

* ``em_validacao`` -> ``consolidado`` after ``consolidar_<criticidade>`` CONSECUTIVE passes (5 normal / 10 critico);
  a failure resets the streak to 0.
* ``consolidado`` -> ``revalidar`` when a change AFFECTS the case; ``revalidar`` -> ``consolidado`` after
  ``revalidar_<criticidade>`` consecutive passes (3 / 6); a failure while revalidating -> ``em_validacao`` (FULL
  threshold again). A failure of a ``consolidado`` case that was run anyway ("rodar tudo") is a regression -> ``em_validacao``.
* A result is ``passou`` | ``falhou`` | ``neutro``. ``neutro`` (an ``erro`` / harness result: nothing was measured about the
  agent) neither counts nor resets.
* AFFECTED = a part the case depends on changed between the reference hashes (the last counted run) and the run's. A case
  with NO declared ``depende_de`` is affected by ANY change (fail-safe), and so is a case with no reference hashes.
  :data:`~app.studio.partes.PARTES_GLOBAIS` affect every case. While ``em_validacao`` an affecting change restarts the
  streak (the earlier passes were for another prompt).

Thresholds are DATA (``eval_consolidacao_config`` rows -> :class:`ConfigConsolidacao`); the defaults below only seed the
migration / the Fake store, they are never consulted in production when a row is missing (the store refuses instead).
"""
from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.studio.partes import PARTES_GLOBAIS

__all__ = [
    "ESTADOS", "CRITICIDADES", "CHAVES_CONFIG", "DEFAULT_CONFIG", "TAGS_CRITICAS", "ConfigConsolidacao",
    "EstadoCaso", "Transicao", "Aplicacao", "estado_inicial", "partes_afetadas", "reconciliar_afetacao",
    "aplicar_resultado", "decidir_selecao", "sugerir_criticidade", "inferir_depende_de", "resumir_estados",
    "resultado_de_status",
]

ESTADOS = ("em_validacao", "consolidado", "revalidar")
CRITICIDADES = ("normal", "critico")
CHAVES_CONFIG = tuple(f"{k}_{c}" for k in ("consolidar", "revalidar") for c in CRITICIDADES)
DEFAULT_CONFIG: dict[str, int] = {
    "consolidar_normal": 5, "consolidar_critico": 10, "revalidar_normal": 3, "revalidar_critico": 6,
}
#: Tags that PROPOSE ``critico`` (a suggestion the owner reviews; the migration applies the same list).
TAGS_CRITICAS: frozenset[str] = frozenset({
    "adversarial", "seguranca", "segurança", "privacidade", "travas", "trava", "firewall-clientes", "integridade",
    "transferencia", "transferência", "lgpd", "pii", "vazamento", "injecao", "injeção",
})


@dataclass(frozen=True)
class ConfigConsolidacao:
    valores: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_CONFIG))

    def __post_init__(self) -> None:
        faltam = [c for c in CHAVES_CONFIG if not isinstance(self.valores.get(c), int) or self.valores[c] < 1]
        if faltam:
            raise ValueError(f"eval_consolidacao_config incompleta/inválida: {faltam}")

    def limite(self, estado: str, criticidade: str) -> int:
        """The streak a case in ``estado`` must reach: ``revalidar`` uses the short one, everything else the full one."""
        if criticidade not in CRITICIDADES:
            raise ValueError(f"criticidade inválida: {criticidade!r}")
        return self.valores[f"{'revalidar' if estado == 'revalidar' else 'consolidar'}_{criticidade}"]


@dataclass(frozen=True)
class EstadoCaso:
    case_id: UUID
    estado: str = "em_validacao"
    sequencia: int = 0
    limite: int = 1
    partes_referencia: Mapping[str, str] | None = None
    hash_referencia: str | None = None
    ultimo_run_id: UUID | None = None


@dataclass(frozen=True)
class Transicao:
    de_estado: str
    para_estado: str
    motivo: str
    sequencia_antes: int
    sequencia_depois: int
    limite: int
    partes_afetadas: tuple[str, ...] = ()
    detalhe: str | None = None


@dataclass(frozen=True)
class Aplicacao:
    estado: EstadoCaso
    transicoes: tuple[Transicao, ...] = ()


def estado_inicial(case_id: UUID, criticidade: str, cfg: ConfigConsolidacao) -> EstadoCaso:
    return EstadoCaso(case_id=case_id, limite=cfg.limite("em_validacao", criticidade))


def resultado_de_status(status: str) -> str:
    """``aprovado`` -> passou; ``reprovado`` -> falhou; anything else (``erro`` / ``pulado`` / ``pendente``) -> neutro."""
    return {"aprovado": "passou", "reprovado": "falhou"}.get(status, "neutro")


# ── affected ──────────────────────────────────────────────────────────────────────────────────────────────


def _casa(dep: str, chave: str) -> bool:
    return fnmatch.fnmatchcase(chave, dep) if "*" in dep else dep == chave


def partes_afetadas(
    depende_de: Sequence[str] | None, atuais: Mapping[str, str] | None, referencia: Mapping[str, str] | None,
) -> tuple[str, ...]:
    """The parts that make a case with ``depende_de`` affected going from ``referencia`` to ``atuais``. ``()`` = unaffected.

    Fail-safe: no declared dependency, or missing hashes on either side, is "affected" (reported as ``("*",)``) unless the
    two hash maps are known and identical."""
    if atuais is None or referencia is None:
        return ("*",)
    mudou = sorted(k for k in set(atuais) | set(referencia) if atuais.get(k) != referencia.get(k))
    if not mudou:
        return ()
    if depende_de is None:
        return tuple(mudou)
    globais = [k for k in mudou if k in PARTES_GLOBAIS]
    declaradas = [k for k in mudou if any(_casa(d, k) for d in depende_de)]
    return tuple(sorted(set(globais) | set(declaradas)))


# ── the machine ──────────────────────────────────────────────────────────────────────────────────────────────


def reconciliar_afetacao(
    est: EstadoCaso, *, criticidade: str, cfg: ConfigConsolidacao, depende_de: Sequence[str] | None,
    atuais: Mapping[str, str] | None, hash_atual: str | None, run_id: UUID | None = None,
    sem_partes: str = "conservadora",
) -> Aplicacao:
    """Apply "a change landed" BEFORE a result: ``consolidado`` -> ``revalidar``; a streak in progress restarts.

    ``sem_partes`` (historical backfill only, where per-part hashes are not recoverable): ``"dono"`` = a bare
    ``compiled_hash`` change affects ONLY a case with no declared dependency; ``"conservadora"`` = it affects every case."""
    if est.partes_referencia is None and est.hash_referencia is None:
        return Aplicacao(est)  # never measured: nothing to compare against, nothing to invalidate
    if atuais is not None and est.partes_referencia is not None:
        afet = partes_afetadas(depende_de, atuais, est.partes_referencia)
    elif hash_atual is not None and est.hash_referencia is not None:
        if hash_atual == est.hash_referencia:
            afet = ()
        elif sem_partes == "dono" and depende_de is not None:
            afet = ()  # per-part hashes unknown: the declared dependencies are the best (and only) statement we have
        else:
            afet = ("*",)
    else:
        afet = ("*",)
    if not afet:
        return Aplicacao(est)
    if est.estado == "consolidado":
        novo = EstadoCaso(est.case_id, "revalidar", 0, cfg.limite("revalidar", criticidade),
                          est.partes_referencia, est.hash_referencia, est.ultimo_run_id)
        return Aplicacao(novo, (Transicao("consolidado", "revalidar", "afetado", est.sequencia, 0, novo.limite, afet),))
    if est.sequencia > 0:  # em_validacao / revalidar mid-streak: the earlier passes judged another prompt
        novo = EstadoCaso(est.case_id, est.estado, 0, cfg.limite(est.estado, criticidade),
                          est.partes_referencia, est.hash_referencia, est.ultimo_run_id)
        return Aplicacao(novo, (Transicao(est.estado, est.estado, "afetado_reinicio", est.sequencia, 0, novo.limite, afet),))
    return Aplicacao(est)


def aplicar_resultado(
    est: EstadoCaso, resultado: str, *, criticidade: str, cfg: ConfigConsolidacao,
    atuais: Mapping[str, str] | None, hash_atual: str | None, run_id: UUID | None = None,
    depende_de: Sequence[str] | None = None, sem_partes: str = "conservadora",
) -> Aplicacao:
    """One execution's result for one case, after reconciling an affecting change. Pure: returns the new state + transitions."""
    if resultado not in ("passou", "falhou", "neutro"):
        raise ValueError(f"resultado inválido: {resultado!r}")
    ap = reconciliar_afetacao(est, criticidade=criticidade, cfg=cfg, depende_de=depende_de, atuais=atuais,
                              hash_atual=hash_atual, run_id=run_id, sem_partes=sem_partes)
    est = ap.estado
    trans = list(ap.transicoes)
    refs = dict(atuais) if atuais is not None else est.partes_referencia
    if resultado == "neutro":
        # nothing measured: the streak is untouched but the reference moves only if it was empty (first sight)
        novo = EstadoCaso(est.case_id, est.estado, est.sequencia, est.limite, est.partes_referencia if est.partes_referencia is not None else refs,
                          est.hash_referencia if est.hash_referencia is not None else hash_atual, run_id or est.ultimo_run_id)
        return Aplicacao(novo, tuple(trans))
    if resultado == "falhou":
        if est.estado == "em_validacao":
            novo_estado, motivo = "em_validacao", "falha"
        else:
            novo_estado, motivo = "em_validacao", "revalidacao_falhou" if est.estado == "revalidar" else "regressao"
        limite = cfg.limite(novo_estado, criticidade)
        novo = EstadoCaso(est.case_id, novo_estado, 0, limite, refs, hash_atual, run_id)
        trans.append(Transicao(est.estado, novo_estado, motivo, est.sequencia, 0, limite))
        return Aplicacao(novo, tuple(trans))
    # passou
    seq = est.sequencia + 1
    limite = cfg.limite(est.estado, criticidade)
    if est.estado != "consolidado" and seq >= limite:
        motivo = "reconsolidado" if est.estado == "revalidar" else "consolidado"
        limite_novo = cfg.limite("consolidado", criticidade)
        novo = EstadoCaso(est.case_id, "consolidado", seq, limite_novo, refs, hash_atual, run_id)
        trans.append(Transicao(est.estado, "consolidado", motivo, est.sequencia, seq, limite_novo))
        return Aplicacao(novo, tuple(trans))
    novo = EstadoCaso(est.case_id, est.estado, seq, limite, refs, hash_atual, run_id)
    trans.append(Transicao(est.estado, est.estado, "acerto", est.sequencia, seq, limite))
    return Aplicacao(novo, tuple(trans))


def decidir_selecao(
    est: EstadoCaso | None, *, criticidade: str, cfg: ConfigConsolidacao, depende_de: Sequence[str] | None,
    atuais: Mapping[str, str] | None, hash_atual: str | None = None,
) -> tuple[bool, Aplicacao | None]:
    """Run the case in a default (not "rodar tudo") run? ``(False, _)`` only for a ``consolidado`` case that is NOT affected.

    The second item is the ``consolidado -> revalidar`` transition to persist when the case IS affected (else ``None``)."""
    if est is None or est.estado != "consolidado":
        return True, None
    ap = reconciliar_afetacao(est, criticidade=criticidade, cfg=cfg, depende_de=depende_de, atuais=atuais, hash_atual=hash_atual)
    if ap.estado.estado == "revalidar":
        return True, ap
    return False, None


# ── proposals ───────────────────────────────────────────────────────────────────────────────────────────────


def sugerir_criticidade(tags: Iterable[str]) -> str:
    return "critico" if any(t.strip().lower() in TAGS_CRITICAS for t in tags) else "normal"


_TOKEN = re.compile(r"[a-z0-9_]+(?:[-.][a-z0-9_]+)*")


def inferir_depende_de(
    *, tags: Sequence[str], asserts: Mapping[str, Any] | None, texto_caso: str, partes_conhecidas: Iterable[str],
) -> tuple[list[str] | None, str]:
    """A heuristic proposal for ``depende_de``. Returns ``(deps | None, porque)`` -- ``None`` = could not infer (the case
    stays fail-safe, affected by any change). Only EXPLICIT signals are used: ``skill:<x>`` / ``ferramenta:<x>`` / ``secao:<x>``
    / ``texto:<x>`` tags, tool names inside the asserts, and a part's own key quoted in the case text. Inferred deps always carry
    the tools/skills the signal names but are never a claim that nothing else matters: they are written with origin ``inferida``
    so the owner can review them. Even a hit is a LOWER BOUND: which sections / texts drive a behaviour cannot be read off a case, so
    proposals are reviewed by the owner before they replace the fail-safe."""
    conhecidas = set(partes_conhecidas)
    deps: list[str] = []
    for t in tags:
        t = t.strip().lower()
        if ":" in t and t.split(":", 1)[0] in {"skill", "ferramenta", "secao", "texto", "decisao", "spec", "skill_ref"}:
            deps.append(t)
    nomes = {p.split(":", 1)[1].lower(): p for p in conhecidas if p.startswith("ferramenta:")}
    skills = {p.split(":", 1)[1].lower(): p for p in conhecidas if p.startswith(("skill:", "skill_ref:"))}

    def _strs(o: Any) -> Iterable[str]:
        if isinstance(o, str):
            yield o
        elif isinstance(o, Mapping):
            for v in o.values():
                yield from _strs(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                yield from _strs(v)

    # ONLY positive signals: a tool the case REQUIRES, a skill it requires opened, the data-subject tool. A PROHIBITED tool
    # (`ferramentas_proibidas`) or a pattern the reply must not match says nothing about which prompt rows drive the behaviour.
    a = asserts or {}
    for s_ in _strs(a.get("ferramentas_incluem", [])):
        if s_.lower() in nomes:
            deps.append(nomes[s_.lower()])
    for s_ in _strs(a.get("skill_aberta_antes_de", [])):
        if s_.lower() in skills:
            deps.append(skills[s_.lower()])
    if a.get("solicitacao_titular") and "registrar_solicitacao_titular" in nomes:
        deps.append(nomes["registrar_solicitacao_titular"])
    corpo = (texto_caso or "").lower()
    toks = set(_TOKEN.findall(corpo))
    for p in conhecidas:
        tipo, _, chave = p.partition(":")
        if tipo in {"secao", "texto", "skill", "skill_ref", "decisao"} and chave and chave.lower() in toks:
            deps.append(p)
    deps = sorted(set(deps))
    if not deps:
        return None, "sem sinal explícito (tag tipada, ferramenta nos asserts ou chave citada)"
    return deps, "tags tipadas / ferramentas nos asserts / chaves citadas no caso"


def resumir_estados(estados: Iterable[str]) -> dict[str, int]:
    out = {e: 0 for e in ESTADOS}
    for e in estados:
        out[e] = out.get(e, 0) + 1
    return out
