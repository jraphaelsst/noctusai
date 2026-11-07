"""Loader + query API for the BR tax-parameter registry (see package docstring)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DATA_DIR = Path(__file__).parent
FAMILIES = ("simples", "mei", "nfse", "reforma_tributaria", "obrigacoes")
Unit = Literal["pct", "brl_centavos", "dia_do_mes", "date", "ratio", "text", "meses"]
Tier = Literal["norma", "orgao_oficial", "publicacao_tecnica", "especialista", "pratica"]
Regime = Literal["simples", "mei", "lucro_presumido", "lucro_real", "*"]


class ParamRegistryError(ValueError):
    """The registry data is invalid (message names file + key)."""


class ParamNotDefined(LookupError):
    def __init__(self, key: str, on: date):
        super().__init__(f"tax parameter {key!r} is not defined on {on.isoformat()}")
        self.key, self.on = key, on


class ParamAmbiguous(LookupError):
    def __init__(self, key: str, on: date, n: int):
        super().__init__(f"tax parameter {key!r} matches {n} rows on {on.isoformat()}; pass scope= to disambiguate")
        self.key, self.on = key, on


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    regime: list[Regime] = Field(default_factory=lambda: ["*"])
    anexo: Optional[str] = None


class ParamRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    value: Any
    unit: Unit
    scope: Scope = Field(default_factory=Scope)
    vigencia_de: date
    vigencia_ate: Optional[date] = None
    norma: str
    fonte_url: list[str] = Field(min_length=1)
    tier: Tier
    verificado_em: date
    verificado_por: str
    revalidar_em: Optional[date] = None
    notas: Optional[str] = None


class ParamValue(BaseModel):
    key: str
    value: Any
    unit: str
    norma: str
    fonte_url: list[str]
    tier: str
    verificado_em: date
    vigencia_de: date
    vigencia_ate: Optional[date]
    scope: dict


class StaleRow(BaseModel):
    key: str
    scope: dict
    reason: Literal["verificacao_vencida", "vigencia_terminando", "vigencia_encerrada_sem_sucessor"]
    verificado_em: date
    vigencia_ate: Optional[date]
    dias: int
    fonte_url: list[str]
    norma: str


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_age_dias: dict[str, int]
    horizonte_vigencia_dias: int


def _no_floats(v: Any, where: str) -> None:
    if isinstance(v, float):
        raise ParamRegistryError(f"{where}: float value {v!r} refused (money = int centavos, rates = Decimal string)")
    if isinstance(v, list):
        for i in v:
            _no_floats(i, where)


def _overlap(a: ParamRow, b: ParamRow) -> bool:
    a_end = a.vigencia_ate or date.max
    b_end = b.vigencia_ate or date.max
    return a.vigencia_de <= b_end and b.vigencia_de <= a_end


def _regimes_intersect(a: Scope, b: Scope) -> bool:
    ra, rb = set(a.regime), set(b.regime)
    return bool(ra & rb) or "*" in ra or "*" in rb


class Registry:
    def __init__(self, rows: list[ParamRow], policy: Policy):
        self.rows, self.policy = rows, policy

    def _matching(self, key: str, on: date, scope: Optional[dict]) -> list[ParamRow]:
        out = []
        for r in self.rows:
            if r.key != key or r.tier == "pratica":
                continue
            if r.vigencia_de > on or (r.vigencia_ate is not None and r.vigencia_ate < on):
                continue
            if scope:
                reg = scope.get("regime")
                if reg is not None and reg not in r.scope.regime and "*" not in r.scope.regime:
                    continue
                if "anexo" in scope and r.scope.anexo != scope["anexo"]:
                    continue
            out.append(r)
        return out


def _to_value(r: ParamRow) -> ParamValue:
    return ParamValue(key=r.key, value=r.value, unit=r.unit, norma=r.norma, fonte_url=r.fonte_url, tier=r.tier,
                      verificado_em=r.verificado_em, vigencia_de=r.vigencia_de, vigencia_ate=r.vigencia_ate,
                      scope=r.scope.model_dump())


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ParamRegistryError(f"{path.name}: invalid YAML: {exc}") from exc


def _build(path: Path, today: date) -> Registry:
    pol_raw = _load_yaml(path / "_policy.yaml")
    try:
        policy = Policy(**pol_raw)
    except (ValidationError, TypeError) as exc:
        raise ParamRegistryError(f"_policy.yaml: {exc}") from exc
    rows: list[ParamRow] = []
    for fam in FAMILIES:
        f = path / f"{fam}.yaml"
        if not f.exists():
            continue
        doc = _load_yaml(f) or {}
        extra = set(doc) - {"rows"}
        if extra:
            raise ParamRegistryError(f"{f.name}: unknown top-level fields {sorted(extra)}")
        for raw in doc.get("rows") or []:
            key = raw.get("key", "?") if isinstance(raw, dict) else "?"
            if isinstance(raw, dict):
                _no_floats(raw.get("value"), f"{f.name}:{key}")
            try:
                row = ParamRow(**raw)
            except (ValidationError, TypeError) as exc:
                raise ParamRegistryError(f"{f.name}:{key}: {exc}") from exc
            if row.verificado_em > today:
                raise ParamRegistryError(f"{f.name}:{key}: verificado_em {row.verificado_em} is in the future")
            if row.tier == "especialista" and len(row.fonte_url) < 2:
                raise ParamRegistryError(f"{f.name}:{key}: tier especialista requires >=2 fonte_url")
            if row.vigencia_ate is not None and row.vigencia_ate < row.vigencia_de:
                raise ParamRegistryError(f"{f.name}:{key}: vigencia_ate before vigencia_de")
            if row.unit == "ratio" or row.unit == "pct":
                try:
                    Decimal(str(row.value))
                except Exception as exc:
                    raise ParamRegistryError(f"{f.name}:{key}: {row.unit} value must be a Decimal string") from exc
            for other in rows:
                if other.key == row.key and _regimes_intersect(other.scope, row.scope) and other.scope.anexo == row.scope.anexo \
                        and _overlap(other, row):
                    raise ParamRegistryError(f"{f.name}:{key}: overlapping vigencia for the same key+scope")
            rows.append(row)
    return Registry(rows, policy)


@lru_cache(maxsize=8)
def _cached(path: str) -> Registry:
    return _build(Path(path), date.today())


def load_registry(path: Optional[Path] = None, *, today: Optional[date] = None) -> Registry:
    """Cached load of the shipped data (or a fixture dir). Passing ``today`` bypasses the cache (test clock)."""
    p = Path(path) if path else DATA_DIR
    if today is not None:
        return _build(p, today)
    return _cached(str(p.resolve()))


def param(key: str, *, on: date, scope: Optional[dict] = None, registry: Optional[Registry] = None) -> ParamValue:
    reg = registry or load_registry()
    m = reg._matching(key, on, scope)
    if not m:
        raise ParamNotDefined(key, on)
    if len(m) > 1:
        raise ParamAmbiguous(key, on, len(m))
    return _to_value(m[0])


def params_for(prefix: str, *, on: date, scope: Optional[dict] = None,
               registry: Optional[Registry] = None) -> dict[str, ParamValue]:
    reg = registry or load_registry()
    out: dict[str, ParamValue] = {}
    for k in sorted({r.key for r in reg.rows if r.key.startswith(prefix)}):
        try:
            out[k] = param(k, on=on, scope=scope, registry=reg)
        except ParamNotDefined:
            continue
    return out


def _fresh_until(r: ParamRow, policy: Policy) -> date:
    return r.revalidar_em or (r.verificado_em + timedelta(days=policy.max_age_dias[r.tier]))


def stale_params(today: date, policy: Optional[Policy] = None, *, registry: Optional[Registry] = None) -> list[StaleRow]:
    reg = registry or load_registry()
    pol = policy or reg.policy
    out: list[StaleRow] = []

    def add(r: ParamRow, reason: str, dias: int) -> None:
        out.append(StaleRow(key=r.key, scope=r.scope.model_dump(), reason=reason, verificado_em=r.verificado_em,
                            vigencia_ate=r.vigencia_ate, dias=dias, fonte_url=r.fonte_url, norma=r.norma))

    in_force = [r for r in reg.rows if r.tier != "pratica" and r.vigencia_de <= today
                and (r.vigencia_ate is None or r.vigencia_ate >= today)]
    for r in in_force:
        due = _fresh_until(r, pol)
        if today > due:
            add(r, "verificacao_vencida", (today - due).days)
    groups: dict[tuple, list[ParamRow]] = {}
    for r in reg.rows:
        if r.tier != "pratica":
            groups.setdefault((r.key, tuple(sorted(r.scope.regime)), r.scope.anexo), []).append(r)
    for rows in groups.values():
        last = max(rows, key=lambda r: r.vigencia_de)
        if last.vigencia_ate is None:
            continue
        left = (last.vigencia_ate - today).days
        if left < 0:
            add(last, "vigencia_encerrada_sem_sucessor", -left)
        elif left <= pol.horizonte_vigencia_dias:
            add(last, "vigencia_terminando", left)
    return out


def staleness_warning(pv: ParamValue, today: date, *, registry: Optional[Registry] = None) -> Optional[dict]:
    """A ``warnings[]`` entry when an in-force param is past its verification age (it still computes), else None."""
    reg = registry or load_registry()
    for s in stale_params(today, registry=reg):
        if s.key == pv.key and s.reason == "verificacao_vencida":
            idade = (today - pv.verificado_em).days
            return {"code": "parametro_desatualizado", "severity": "warning",
                    "message": f"Parâmetro {pv.key} verificado há {idade} dias ({pv.norma}); revalide a fonte.",
                    "action": "Peça ao contador/agente de contabilidade para revalidar o parâmetro.",
                    "details": {"key": pv.key, "verificado_em": pv.verificado_em.isoformat(), "dias": idade}}
    return None
