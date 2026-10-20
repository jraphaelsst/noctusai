"""Multi-turn mechanism evals that gate a publish (Julia v2 A-EVAL; CONTRACT 3.5 E4 and 10.3).

Two suites share ``eval_cases``:

* ``mecanismo`` -- a scripted multi-turn lead conversation (``roteiro``) graded ONLY by deterministic,
  code-checked ``asserts`` on the END STATE (stage, registered criteria, handoff, ...). The path (tool names,
  skill order) is asserted only where the path IS the requirement. No judge. A case passes only if ALL ``k``
  executions pass (pass^k -- a flaky mechanism is a broken mechanism). The suite must be 100% pass^k, driven by
  the LIVE model, to open the publish gate.
* ``comportamento`` -- the existing judge suite. Advisory (shown, never blocking) unless the agent sets
  ``comportamento_bloqueia``.

The runner drives turns through :class:`app.studio.eval_driver.EvalTurnDriver` (A-RT provides the real adapter;
CI uses the scripted fake). Nothing here holds eval CONTENT: cases are DB rows (seeded later) and fixtures in
tests are synthetic. Failures are reported as CODES (assert name + tool/criterion key), never reply text or
prompt content (IP, CONTRACT 0.4).
"""
from __future__ import annotations

import dataclasses
import functools
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.studio.eval_driver import (
    Estado,
    EvalTurnDriver,
    Handoff,
    Mensagem,
    ThreadState,
    ToolCall,
    TurnOutcome,
    Violation,
    reiniciar,
)
from app.studio.eval_sinteticos import TokenSinteticoDesconhecido, validar_tokens

__all__ = [
    "ASSERT_NAMES",
    "SUITES",
    "K_MIN",
    "K_MAX",
    "RoteiroInvalido",
    "AssertInvalido",
    "Falha",
    "Traco",
    "Caso",
    "ExecucaoResultado",
    "CasoResultado",
    "SuiteResultado",
    "MecanismoGateRun",
    "MecanismoRequisito",
    "PortaoMecanismo",
    "pass_k",
    "validar_asserts",
    "validar_roteiro",
    "validar_caso_mecanismo",
    "fatiar_em_turnos",
    "avaliar_asserts",
    "executar_suite",
    "decidir_portao",
]

SUITES = ("mecanismo", "comportamento")
K_MIN, K_MAX = 1, 10
VIOLACAO_VAZAMENTO_PREFIXO = "vazamento"

ASSERT_NAMES = (
    "ferramentas_incluem",
    "ferramentas_proibidas",
    "estagio_final",
    "criterios_registrados",
    "ofertas_por_lote",
    "sem_violacoes",
    "identificacao_completa",
    "handoff_para",
    "sem_vazamento",
    "skill_aberta_antes_de",
)
#: ``abrir_skill`` is the tool whose call names the opened skill.
FERRAMENTA_ABRIR_SKILL = "abrir_skill"


@functools.cache
def arg_skill() -> str:
    """The argument of ``abrir_skill`` that names the skill, DERIVED from the tool's strict argument model
    (``app.channels.tool_registry.TOOLS``) -- never a second hand-kept string that can drift from the schema the
    model is actually given. The model has exactly one required field; anything else is a registry change this
    assert must be revisited for, so it fails loudly. Resolved on first use (``tool_registry`` imports
    ``app.studio.models``, which imports this module)."""
    from app.channels.tool_registry import TOOLS

    campos = [n for n, f in TOOLS[FERRAMENTA_ABRIR_SKILL].args.model_fields.items() if f.is_required()]
    if len(campos) != 1:
        raise RuntimeError(f"{FERRAMENTA_ABRIR_SKILL}: esperado 1 argumento obrigatório, obtido {campos}")
    return campos[0]


class RoteiroInvalido(ValueError):
    pass


class AssertInvalido(ValueError):
    pass


# ── validation (fail closed: an unknown assert key is an error, never a silent pass) ────────────────────


def _lista_str(nome: str, valor: Any) -> None:
    if not isinstance(valor, list) or not valor or not all(isinstance(x, str) and x for x in valor):
        raise AssertInvalido(f"{nome}: lista não vazia de textos")


def validar_asserts(asserts: Any, *, onde: str = "asserts") -> None:
    if not isinstance(asserts, dict) or not asserts:
        raise AssertInvalido(f"{onde}: objeto não vazio")
    for nome, valor in asserts.items():
        if nome not in ASSERT_NAMES:
            raise AssertInvalido(f"{onde}: assert desconhecido {nome!r}")
        if nome in ("ferramentas_incluem", "ferramentas_proibidas", "criterios_registrados"):
            _lista_str(nome, valor)
        elif nome in ("estagio_final", "handoff_para"):
            if not isinstance(valor, str) or not valor:
                raise AssertInvalido(f"{nome}: texto")
        elif nome == "ofertas_por_lote":
            if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
                raise AssertInvalido("ofertas_por_lote: inteiro >= 1")
        elif nome == "sem_violacoes":
            if valor is not True and not (
                isinstance(valor, list) and valor and all(isinstance(x, str) and x for x in valor)
            ):
                raise AssertInvalido("sem_violacoes: true ou lista de regras")
        elif nome == "identificacao_completa":
            if not isinstance(valor, bool):
                raise AssertInvalido("identificacao_completa: booleano")
        elif nome == "sem_vazamento":
            if valor is not True:
                raise AssertInvalido("sem_vazamento: true")
        elif nome == "skill_aberta_antes_de":
            itens = valor if isinstance(valor, list) else [valor]
            if not itens or not all(
                isinstance(i, dict) and set(i) == {"skill", "ferramenta"}
                and isinstance(i["skill"], str) and i["skill"] and isinstance(i["ferramenta"], str) and i["ferramenta"]
                for i in itens
            ):
                raise AssertInvalido("skill_aberta_antes_de: {skill, ferramenta} ou lista")


def validar_roteiro(roteiro: Any) -> None:
    if not isinstance(roteiro, dict):
        raise RoteiroInvalido("roteiro: objeto")
    turnos = roteiro.get("turnos")
    if not isinstance(turnos, list) or not turnos:
        raise RoteiroInvalido("roteiro.turnos: lista não vazia")
    for i, t in enumerate(turnos):
        if not isinstance(t, dict) or not isinstance(t.get("lead"), str) or not t["lead"].strip():
            raise RoteiroInvalido(f"roteiro.turnos[{i}].lead: texto")
        try:
            validar_tokens([(f"roteiro.turnos[{i}].lead", t["lead"])])
        except TokenSinteticoDesconhecido as exc:
            raise RoteiroInvalido(str(exc)) from exc
        if "esperar" in t:
            try:
                validar_asserts(t["esperar"], onde=f"roteiro.turnos[{i}].esperar")
            except AssertInvalido as exc:
                raise RoteiroInvalido(str(exc)) from exc
    cat = roteiro.get("catalogo", [])
    if not isinstance(cat, list) or not all(isinstance(c, dict) for c in cat):
        raise RoteiroInvalido("roteiro.catalogo: lista de objetos")
    can = roteiro.get("canarios", [])
    if not isinstance(can, list) or not all(isinstance(c, str) and len(c) >= 4 for c in can):
        raise RoteiroInvalido("roteiro.canarios: lista de textos (>= 4 caracteres)")
    for chave in ("estado_inicial", "fixture"):
        if chave in roteiro and not isinstance(roteiro[chave], dict):
            raise RoteiroInvalido(f"roteiro.{chave}: objeto")
    extra = set(roteiro.get("estado_inicial") or {}) - {f.name for f in dataclasses.fields(Estado)}
    if extra:
        raise RoteiroInvalido(f"roteiro.estado_inicial: campos desconhecidos {sorted(extra)}")


def validar_caso_mecanismo(*, k: int, roteiro: Any, asserts: Any, **conteudo_sintetico: Any) -> None:
    """The one validator every store calls before writing a ``mecanismo`` case. Also refuses personal data
    (Meta 4.7: fixtures are synthetic)."""
    from app.studio.eval_pii import recusar_pii

    if isinstance(k, bool) or not isinstance(k, int) or not (K_MIN <= k <= K_MAX):
        raise ValueError(f"k deve estar entre {K_MIN} e {K_MAX}")
    validar_roteiro(roteiro)
    validar_asserts(asserts)
    recusar_pii(roteiro=roteiro, asserts=asserts, **conteudo_sintetico)


def fatiar_em_turnos(fatos: Sequence[str], *, esperar_por_turno: dict[int, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Sharded scenario: information arrives piecemeal. One fact per lead turn (the fully-specified request
    is split so the agent must ask for what is missing instead of receiving it all at once). ``esperar_por_turno``
    maps a turn index to intermediate asserts (e.g. ``{0: {"ferramentas_proibidas": ["oferecer_imoveis"]}}`` --
    no offer before the minimum is known)."""
    if not fatos or not all(isinstance(f, str) and f.strip() for f in fatos):
        raise RoteiroInvalido("fatos: lista não vazia de textos")
    esperar_por_turno = esperar_por_turno or {}
    turnos: list[dict[str, Any]] = []
    for i, fato in enumerate(fatos):
        turno: dict[str, Any] = {"lead": fato}
        if i in esperar_por_turno:
            turno["esperar"] = esperar_por_turno[i]
        turnos.append(turno)
    return turnos


# ── trace + asserts ───────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Falha:
    assert_nome: str
    codigo: str

    def to_dict(self) -> dict[str, str]:
        return {"assert": self.assert_nome, "codigo": self.codigo}


@dataclass
class Traco:
    """Everything observed across the turns of one execution (cumulative)."""

    bolhas: list[str] = field(default_factory=list)
    ferramentas: list[ToolCall] = field(default_factory=list)
    acoes: list[str] = field(default_factory=list)
    violacoes: list[Violation] = field(default_factory=list)
    estado: Estado = field(default_factory=Estado)
    handoff: Handoff | None = None
    canarios: tuple[str, ...] = ()

    def absorver(self, o: TurnOutcome) -> None:
        self.bolhas.extend(o.bolhas)
        self.ferramentas.extend(o.ferramentas)
        self.acoes.extend(o.acoes)
        self.violacoes.extend(o.violacoes)
        self.estado = o.estado
        if o.handoff is not None:
            self.handoff = o.handoff


def avaliar_asserts(asserts: dict[str, Any], t: Traco, *, prefixo: str = "") -> list[Falha]:
    """Pure: every failed assert as a code. Empty list == all passed."""
    falhas: list[Falha] = []

    def falha(nome: str, codigo: str) -> None:
        falhas.append(Falha(nome, f"{prefixo}{codigo}"))

    chamadas = [c.nome for c in t.ferramentas]
    for nome, valor in asserts.items():
        if nome == "ferramentas_incluem":
            for f in valor:
                if f not in chamadas:
                    falha(nome, f"ausente:{f}")
        elif nome == "ferramentas_proibidas":
            for f in valor:
                if f in chamadas:
                    falha(nome, f"chamada:{f}")
        elif nome == "estagio_final":
            if t.estado.estagio != valor:
                falha(nome, f"esperado:{valor}|obtido:{t.estado.estagio}")
        elif nome == "criterios_registrados":
            for c in valor:
                if c not in t.estado.criterios:
                    falha(nome, f"nao_registrado:{c}")
        elif nome == "ofertas_por_lote":
            for i, lote in enumerate(t.estado.lotes):
                if len(lote) > valor:
                    falha(nome, f"lote{i + 1}:{len(lote)}>{valor}")
        elif nome == "sem_violacoes":
            regras = {v.regra for v in t.violacoes}
            alvo = regras if valor is True else regras & set(valor)
            for r in sorted(alvo):
                falha(nome, f"violacao:{r}")
        elif nome == "identificacao_completa":
            completa = not t.estado.identificacao_faltando
            if completa != valor:
                falha(nome, "completa" if completa else "faltando:" + ",".join(t.estado.identificacao_faltando))
        elif nome == "handoff_para":
            if t.handoff is None:
                falha(nome, "sem_handoff")
            elif t.handoff.para != valor:
                falha(nome, f"esperado:{valor}|obtido:{t.handoff.para}")
        elif nome == "sem_vazamento":
            texto = "\n".join(t.bolhas).lower()
            for i, c in enumerate(t.canarios):
                if c.lower() in texto:
                    falha(nome, f"canario:{i + 1}")
            for v in t.violacoes:
                if v.regra.startswith(VIOLACAO_VAZAMENTO_PREFIXO):
                    falha(nome, f"violacao:{v.regra}")
        elif nome == "skill_aberta_antes_de":
            for par in valor if isinstance(valor, list) else [valor]:
                skill, alvo = par["skill"], par["ferramenta"]
                primeira = next((i for i, c in enumerate(t.ferramentas) if c.nome == alvo), None)
                if primeira is None:
                    continue  # the path requirement binds only when the tool ran (pair with ferramentas_incluem)
                aberta = any(
                    c.nome == FERRAMENTA_ABRIR_SKILL and c.args.get(arg_skill()) == skill
                    for c in t.ferramentas[:primeira]
                )
                if not aberta:
                    falha(nome, f"{skill}:antes_de:{alvo}")
    return falhas


# ── pass^k ────────────────────────────────────────────────────────────────────────────────────────────────


def pass_k(resultados: Sequence[bool], k: int) -> bool:
    """pass^k: ALL ``k`` executions passed. Fewer than ``k`` executions (a cut-short case) is never a pass."""
    return len(resultados) == k and all(resultados)


# ── runner ────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Caso:
    id: UUID
    slug: str
    k: int
    roteiro: dict[str, Any]
    asserts: dict[str, Any]


@dataclass(frozen=True)
class ExecucaoResultado:
    indice: int
    status: str  # aprovado | reprovado | erro | pulado
    falhas: tuple[Falha, ...] = ()
    ferramentas: tuple[str, ...] = ()
    custo_usd: float = 0.0
    duracao_ms: int = 0


@dataclass(frozen=True)
class CasoResultado:
    caso: Caso
    execucoes: tuple[ExecucaoResultado, ...]

    @property
    def passou(self) -> bool:
        return pass_k([e.status == "aprovado" for e in self.execucoes], self.caso.k)

    @property
    def taxa(self) -> float:
        ex = [e for e in self.execucoes if e.status != "pulado"]
        return sum(1 for e in ex if e.status == "aprovado") / len(ex) if ex else 0.0


@dataclass(frozen=True)
class SuiteResultado:
    casos: tuple[CasoResultado, ...]
    custo_usd: float
    orcamento_excedido: bool
    #: every case ran all of its k executions (nothing skipped by the cost cap or an early stop elsewhere)
    completo: bool

    @property
    def aprovado(self) -> bool:
        """Suite 100% pass^k, complete, under budget, at least one case."""
        return bool(self.casos) and self.completo and not self.orcamento_excedido and all(c.passou for c in self.casos)

    @property
    def casos_aprovados(self) -> int:
        return sum(1 for c in self.casos if c.passou)


class _Orcamento:
    def __init__(self, limite_usd: float | None) -> None:
        self.limite = limite_usd
        self.total = 0.0
        self.excedido = False

    def add(self, custo: float | None) -> None:
        if custo:
            self.total += custo
        if self.limite is not None and self.total >= self.limite:
            self.excedido = True


def _estado_inicial(roteiro: dict[str, Any]) -> Estado:
    raw = dict(roteiro.get("estado_inicial") or {})
    if "lotes" in raw:
        raw["lotes"] = tuple(tuple(x) for x in raw["lotes"])
    if "identificacao_faltando" in raw:
        raw["identificacao_faltando"] = tuple(raw["identificacao_faltando"])
    return Estado(**raw)


async def _executar_execucao(
    caso: Caso, driver: EvalTurnDriver, indice: int, orcamento: _Orcamento,
) -> ExecucaoResultado:
    inicio = time.monotonic()
    reiniciar(driver)
    roteiro = caso.roteiro
    thread = ThreadState(
        catalogo=tuple(roteiro.get("catalogo") or ()),
        estado=_estado_inicial(roteiro),
        historico=(),
        fixture=dict(roteiro.get("fixture") or {}),
    )
    traco = Traco(canarios=tuple(roteiro.get("canarios") or ()))
    falhas: list[Falha] = []
    custo = 0.0

    def pronto(status: str) -> ExecucaoResultado:
        return ExecucaoResultado(
            indice=indice, status=status, falhas=tuple(falhas),
            ferramentas=tuple(c.nome for c in traco.ferramentas), custo_usd=custo,
            duracao_ms=int((time.monotonic() - inicio) * 1000),
        )

    for i, turno in enumerate(roteiro["turnos"]):
        try:
            outcome = await driver.executar_turno(thread, turno["lead"])
        except Exception as exc:  # a driver failure is a RESULT (erro), never swallowed or re-raised as a pass
            falhas.append(Falha("driver", f"erro_turno{i + 1}:{type(exc).__name__}"))
            return pronto("erro")
        custo += outcome.custo_usd or 0.0
        orcamento.add(outcome.custo_usd)
        traco.absorver(outcome)
        thread = ThreadState(
            catalogo=thread.catalogo,
            estado=outcome.estado,
            historico=thread.historico + (
                Mensagem("lead", turno["lead"]),
                *(Mensagem("agente", b) for b in outcome.bolhas),
            ),
            fixture=thread.fixture,
        )
        if "esperar" in turno:
            falhas.extend(avaliar_asserts(turno["esperar"], traco, prefixo=f"turno{i + 1}:"))
        if orcamento.excedido and i < len(roteiro["turnos"]) - 1:
            falhas.append(Falha("orcamento", "excedido"))
            return pronto("erro")
    falhas.extend(avaliar_asserts(caso.asserts, traco))
    return pronto("reprovado" if falhas else "aprovado")


async def executar_suite(
    casos: Sequence[Caso],
    driver: EvalTurnDriver,
    *,
    limite_usd: float | None = None,
    parar_no_primeiro_erro: bool = True,
) -> SuiteResultado:
    """Run every case k times through ``driver``. Cost cap: once ``limite_usd`` is reached no new execution
    starts; the rest are ``pulado`` and the suite is NOT complete (so never approved).

    ``parar_no_primeiro_erro``: after the first failed execution of a case the remaining ones are skipped (the
    case cannot pass pass^k anymore) -- that is not an incomplete suite, the verdict is already final.
    """
    orcamento = _Orcamento(limite_usd)
    resultados: list[CasoResultado] = []
    completo = True
    for caso in casos:
        execs: list[ExecucaoResultado] = []
        condenado = False
        for n in range(1, caso.k + 1):
            if condenado and parar_no_primeiro_erro:
                execs.append(ExecucaoResultado(indice=n, status="pulado"))
                continue
            if orcamento.excedido:
                execs.append(ExecucaoResultado(indice=n, status="pulado"))
                completo = False
                continue
            res = await _executar_execucao(caso, driver, n, orcamento)
            execs.append(res)
            if res.status != "aprovado":
                condenado = True
        resultados.append(CasoResultado(caso=caso, execucoes=tuple(execs)))
    return SuiteResultado(
        casos=tuple(resultados), custo_usd=round(orcamento.total, 4),
        orcamento_excedido=orcamento.excedido, completo=completo,
    )


# ── publish gate ──────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MecanismoGateRun:
    id: UUID
    compiled_hash: str
    status: str
    driver: str
    completa: bool
    aprovado: bool
    orcamento_excedido: bool
    total_casos: int
    casos_aprovados: int


@dataclass(frozen=True)
class MecanismoRequisito:
    """What the publish gate needs to know about the mechanism suite of one agent/version."""

    #: the agent has ``exige_mecanismo`` OR at least one active mecanismo case
    exigido: bool = False
    casos_ativos: int = 0
    #: ``agents.comportamento_bloqueia`` -- the judge suite blocks publish only when set
    comportamento_bloqueia: bool = False
    run: MecanismoGateRun | None = None


@dataclass(frozen=True)
class PortaoMecanismo:
    liberado: bool
    codigo: str
    run_id: UUID | None = None


def decidir_portao(req: MecanismoRequisito, compiled_hash: str) -> PortaoMecanismo:
    """Publish needs, for the CURRENT compiled hash, a finished, complete, under-budget, LIVE-driver run in
    which every mecanismo case passed pass^k. Fail closed: an empty suite never reads as green."""
    if not req.exigido:
        return PortaoMecanismo(True, "nao_exigido")
    if req.casos_ativos < 1:
        return PortaoMecanismo(False, "sem_casos")
    r = req.run
    if r is None:
        return PortaoMecanismo(False, "sem_execucao")
    if r.compiled_hash != compiled_hash:
        return PortaoMecanismo(False, "hash_diferente", r.id)
    if r.driver != "live":
        return PortaoMecanismo(False, "driver_nao_live", r.id)
    if r.status != "concluida":
        return PortaoMecanismo(False, "nao_concluida", r.id)
    if r.orcamento_excedido:
        return PortaoMecanismo(False, "orcamento_excedido", r.id)
    if not r.completa:
        return PortaoMecanismo(False, "incompleta", r.id)
    if not r.aprovado or r.casos_aprovados != r.total_casos or r.total_casos < req.casos_ativos:
        return PortaoMecanismo(False, "reprovada", r.id)
    return PortaoMecanismo(True, "ok", r.id)
