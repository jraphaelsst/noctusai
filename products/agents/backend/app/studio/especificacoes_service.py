"""THE one validator of an org's spec values (Julia-line CONTRACT §E2): the studio PUT, the channel/SW PUT, the
compiler re-validation and readiness all call :func:`validar`. Pure (no IO); the settings are read only by
:func:`config_atual`, at call time, and handed down explicitly (no module-level singletons).

Rollout (``SPEC_VALIDATION_MODE``): ``report`` accepts every write and surfaces each invalid stored value as an
``aviso`` ``spec_org_invalida`` (readiness + the org view); ``block`` answers 422 on write, a ``bloqueante`` in
readiness, and the compiler drops the invalid value. Either way nothing is silent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.studio.especificacoes import conflitos_com_regras_fixas
from app.studio.models import SPEC_TIPOS_TEXTO_LIVRE, ConfigValidacao
from app.studio.spec_formatos import ContextoSpec, SpecInvalida, Violacao, validar_valor

__all__ = ["ConfigValidacao", "ResultadoValidacao", "ValoresOrg", "config_atual", "preparar", "validar", "violacoes_armazenadas"]

CHAVE_DOMINIOS = "dominios_permitidos"


def config_atual() -> ConfigValidacao:
    """The deployment's settings, read at call time."""
    from app.config import settings

    hosts = tuple(h.strip().lower() for h in settings.spec_hosts_publicos.split(",") if h.strip())
    return ConfigValidacao(modo=settings.spec_validation_mode, hosts_publicos=hosts)


@dataclass(frozen=True)
class ResultadoValidacao:
    #: ``{chave: value}`` — normalized when valid; the NFKC-trimmed raw text when not (report mode stores it).
    valores: dict[str, str]
    violacoes: tuple[Violacao, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.violacoes

    @property
    def invalidas(self) -> dict[str, tuple[Violacao, ...]]:
        out: dict[str, list[Violacao]] = {}
        for v in self.violacoes:
            out.setdefault(v.chave, []).append(v)
        return {k: tuple(v) for k, v in out.items()}


def _dominios_do_contexto(declaradas: Mapping[str, str], valores: Mapping[str, str]) -> tuple[str, ...]:
    raw = valores.get(CHAVE_DOMINIOS, "")
    if not isinstance(raw, str) or not raw.strip() or declaradas.get(CHAVE_DOMINIOS) != "dominios":
        return ()
    try:
        return tuple(x.strip() for x in validar_valor("dominios", raw).split(",") if x.strip())
    except SpecInvalida:
        return ()


def validar(
    declaradas: Mapping[str, str], valores: Mapping[str, str], *,
    armazenados: Mapping[str, str] | None = None, config: ConfigValidacao | None = None,
) -> ResultadoValidacao:
    """Validate ``valores`` (``{chave: valor}``) against ``declaradas`` (``{chave: tipo}``).

    ``armazenados`` = the org's already stored values: a ``url`` is checked against the org's
    ``dominios_permitidos`` (the value in ``valores`` wins over the stored one). A blank value is the
    "clear" gesture and passes. An undeclared key is the caller's concern (``spec_nao_declarada``)."""
    config = config or ConfigValidacao()
    ctx = ContextoSpec(
        dominios_permitidos=_dominios_do_contexto(declaradas, {**(armazenados or {}), **valores}),
        hosts_publicos=config.hosts_publicos,
    )
    saida: dict[str, str] = {}
    viol: list[Violacao] = []
    for chave, valor in valores.items():
        tipo = declaradas.get(chave)
        if tipo is None or not isinstance(valor, str) or not valor.strip():
            saida[chave] = valor.strip() if isinstance(valor, str) else valor
            continue
        try:
            norm = validar_valor(tipo, valor, ctx)
        except SpecInvalida as exc:
            viol += [Violacao(v.codigo, v.motivo, f"{chave}: {v.mensagem}", chave) for v in exc.violacoes]
            saida[chave] = valor.strip()
            continue
        saida[chave] = norm
        conflitos = conflitos_com_regras_fixas(norm)
        if conflitos:
            viol.append(Violacao(
                "spec_conflita_com_regra_fixa", "regra_fixa",
                f"{chave}: o texto contradiz uma regra fixa da plataforma ({', '.join(conflitos)}).", chave,
            ))
    return ResultadoValidacao(saida, tuple(viol))


def violacoes_armazenadas(
    declaradas: Mapping[str, str], armazenados: Mapping[str, str], *, config: ConfigValidacao | None = None,
) -> tuple[Violacao, ...]:
    """Re-validate what is ALREADY stored (readiness, org view, compiler)."""
    return validar(declaradas, armazenados, config=config).violacoes


@dataclass(frozen=True)
class ValoresOrg:
    """An org's stored values, ready to be put in front of a model (compiler + skill reader use the SAME object)."""

    #: ``{chave: canonical value}``; in block mode an invalid value is dropped (report mode keeps it, as fenced data).
    valores: dict[str, str]
    #: Keys whose value is free text (or undeclared): NEVER inlined -- ``[dado: chave]`` + the data section (E3).
    fenced: frozenset[str]
    invalidas: dict[str, tuple[Violacao, ...]]


def preparar(declaradas: Mapping[str, str], armazenados: Mapping[str, str], config: ConfigValidacao) -> ValoresOrg:
    res = validar(declaradas, {k: v for k, v in armazenados.items() if isinstance(v, str)}, config=config)
    invalidas = res.invalidas
    valores = {k: v for k, v in res.valores.items() if not (config.bloqueia and k in invalidas)}
    fenced = frozenset(k for k in valores if declaradas.get(k) is None or declaradas[k] in SPEC_TIPOS_TEXTO_LIVRE)
    return ValoresOrg(valores, fenced, invalidas)
