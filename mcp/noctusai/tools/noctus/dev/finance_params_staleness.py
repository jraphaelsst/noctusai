"""`noctus.dev.finance_params_staleness` -- the calendar-driven staleness loop of the BR tax-parameter registry.

WHY (owner mandate 2026-11-07: tax parameters stay current with no owner effort). Staleness is driven by
the calendar, not by a diff, so it must NEVER block unrelated work -- but it must never be silent either.
Build triad: construction = skill `noc-tax-params` (the guided re-verification path) + the registry's own
row contract; backstop = keeper `check_finance_params_schema` (judges the diff) + this report (judges the
clock, rolled into `noc-daily-ops`); telemetry = `log=True` appends one auto-improvement drift row per
stale key that self-closes (`resolve_when: finance_param_fresh:<key>`) once the registry stops flagging it.

The registry is loaded from the CHECKED-OUT tree by path (never a possibly-stale editable install), so the
report and the keeper judge the same files.

Depth: `KB § PATTERNS/finance/br-tax-advisor-canon.md` (what the params are) and the skill `noc-tax-params`.
"""
from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from settings import REPO_ROOT

PARAMS_REL = "seed/lib/backend/noctusai_lib/domain/finance/params"
REASONS = ("verificacao_vencida", "vigencia_terminando", "vigencia_encerrada_sem_sucessor")
#: A key with no successor whose ``vigencia_ate`` is within this many days (or already past) escalates.
ESCALATE_DIAS = 15
RESOLVE_PREFIX = "finance_param_fresh:"


def load_registry_module(root: Path | None = None):
    """Import ``registry.py`` of ``root``'s tree under a private module name (stdlib+pydantic+yaml only)."""
    base = Path(root or REPO_ROOT)
    path = base / PARAMS_REL / "registry.py"
    if not path.is_file():
        raise FileNotFoundError(f"finance params registry not found at {path}")
    name = f"_noc_finance_params_registry_{abs(hash(str(path.resolve())))}"
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # pydantic resolves forward refs through sys.modules
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


def _key_label(s) -> str:
    sc = s.scope or {}
    anexo = sc.get("anexo")
    return s.key if not anexo else f"{s.key}[{anexo}]"


def _row(s) -> dict[str, Any]:
    return {"key": s.key, "label": _key_label(s), "scope": s.scope, "reason": s.reason, "norma": s.norma,
            "fonte_url": list(s.fonte_url), "verificado_em": s.verificado_em.isoformat(),
            "vigencia_ate": s.vigencia_ate.isoformat() if s.vigencia_ate else None, "dias": s.dias}


def is_escalation(s) -> bool:
    """No successor and the vigencia ends within ESCALATE_DIAS (or already ended)."""
    if s.reason == "vigencia_encerrada_sem_sucessor":
        return True
    return s.reason == "vigencia_terminando" and s.dias <= ESCALATE_DIAS


def report(today: date | None = None, root: Path | None = None, registry_dir: Path | None = None) -> dict[str, Any]:
    """Pure report. ``status``: ok | stale | escalate | inconclusive (registry unreadable => never green)."""
    today = today or date.today()
    try:
        mod = load_registry_module(root)
        reg = mod.load_registry(registry_dir, today=today) if registry_dir else mod.load_registry(
            Path(root or REPO_ROOT) / PARAMS_REL, today=today)
        stale = mod.stale_params(today, registry=reg)
    except Exception as exc:  # unmeasurable is inconclusive, not red and not green
        return {"ok": False, "status": "inconclusive", "escalate": False, "error": f"{type(exc).__name__}: {exc}",
                "counts": {}, "grouped": {}}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for s in stale:
        grouped[s.reason].append(_row(s))
    stale_keys = sorted({_key_label(s) for s in stale})
    escalate_keys = sorted({_key_label(s) for s in stale if is_escalation(s)})
    escalate = bool(escalate_keys)
    counts = {"total_rows": len(reg.rows), "stale_keys": len(stale_keys),
              **{r: len(grouped.get(r, [])) for r in REASONS}, "escalate_keys": len(escalate_keys)}
    status = "escalate" if escalate else ("stale" if stale else "ok")
    return {"ok": True, "status": status, "escalate": escalate, "today": today.isoformat(), "counts": counts,
            "stale_keys": stale_keys, "escalate_keys": escalate_keys,
            "grouped": {r: grouped[r] for r in REASONS if grouped.get(r)},
            "line": f"{len(stale_keys)} parametros fiscais a reverificar" if stale else "0 parametros fiscais a reverificar"}


def log_telemetry(rep: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """Append one drift row per stale key (+ one run-summary improvement row) to the auto-improvement ledger."""
    from tools.noctus.dev import auto_improvement as ai

    today = today or date.today()
    logged: list[str] = []
    errors: list[str] = []
    seen: set[str] = set()
    for reason, rows in rep.get("grouped", {}).items():
        for r in rows:
            if r["key"] in seen:
                continue
            seen.add(r["key"])
            target = f"finance-params:{r['key']}"
            if any(e.get("target") == target for e in ai.query(target=target, kind="drift", open_only=True,
                                                               skip_reconcile=True)):
                continue  # already tracked and still open: no daily duplicate
            out = ai.log_entry(
                scope="scoped", kind="drift", target=target, agent="tooling-engineer",
                description=(f"Parametro fiscal {r['label']} precisa de reverificacao ({reason}, {r['dias']} dias; "
                             f"{r['norma']}). Rode a skill noc-tax-params."),
                resolve_when=f"{RESOLVE_PREFIX}{r['key']}", source_ref="finance_params_staleness",
            )
            (logged if out.get("ok") else errors).append(r["key"] if out.get("ok") else f"{r['key']}: {out.get('error')}")
    c = rep.get("counts", {})
    summ = ai.log_entry(
        scope="scoped", kind="improvement", target="finance-params:run-summary", agent="tooling-engineer",
        description=(f"finance_params_staleness {today.isoformat()}: stale={c.get('stale_keys', 0)} "
                     f"expiring={c.get('vigencia_terminando', 0)} ended={c.get('vigencia_encerrada_sem_sucessor', 0)} "
                     f"total_rows={c.get('total_rows', 0)} escalate={rep.get('escalate')}"),
        status="closed", source_ref="finance_params_staleness",
    )
    if not summ.get("ok"):
        errors.append(f"run-summary: {summ.get('error')}")
    return {"logged": logged, "errors": errors}


def finance_params_staleness(action: str = "report", log: bool = False, today: str | None = None,
                             root: Path | None = None) -> dict[str, Any]:
    if action != "report":
        return {"ok": False, "error": f"unknown action {action!r}; only 'report' exists"}
    try:
        day = date.fromisoformat(today) if today else None
    except ValueError:
        return {"ok": False, "error": f"today must be ISO YYYY-MM-DD; got {today!r}"}
    rep = report(day, root)
    if log and rep.get("ok"):
        rep["telemetry"] = log_telemetry(rep, day)
    return rep


def register(server) -> None:
    @server.tool(
        name="noctus.dev.finance_params_staleness",
        description=(
            "Calendar-driven staleness report of the BR tax-parameter registry (seed finance/params). "
            "action='report' (default): rows grouped by verificacao_vencida / vigencia_terminando / "
            "vigencia_encerrada_sem_sucessor (key, norma, fonte_url, dias) + counts + `escalate` (a key with no "
            "successor whose vigencia ends within 15 days or already ended). log=True appends one auto-improvement "
            "drift row per stale key (resolve_when finance_param_fresh:<key>) + a run summary. status "
            "ok|stale|escalate|inconclusive (registry unreadable). Never blocks work. Fix via skill noc-tax-params."
        ),
    )
    def _finance_params_staleness(action: str = "report", log: bool = False, today: str | None = None) -> dict:
        return finance_params_staleness(action=action, log=log, today=today)


__all__ = ["finance_params_staleness", "report", "log_telemetry", "load_registry_module", "is_escalation",
           "register", "RESOLVE_PREFIX", "PARAMS_REL"]
