"""`fin_dre_settings` -- the per-store mapping of every PROVISIONAL accounting choice (CONTRACT §10.3 / §10.5).

D48: a choice an accountant may overrule is DATA, never code. One row per org (created lazily on the first PUT;
until then `GET` answers the defaults with `persisted=False`). Nothing here moves money -- it only decides which
DRE line a fact lands on. `choice_meta` shape (one JSON object per choice name)::

    {"gateway_fee_line": {"provisional": false, "confirmed_by": "<user id>", "confirmed_at": "<iso>", "note": "..."}}

A choice with no entry is provisional (the default state of every choice). Changing a choice's VALUE returns it to
provisional unless the same request confirms it; confirming clears `provisional` (the accountant's sign-off).
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, first, new_id, now_iso
from .errors import invalid
from .types import DreLine, TaxRegime, values

#: choice name -> default DRE line (CONTRACT §10.5 items 3-4). The order is the order the checklist shows.
CHOICE_DEFAULTS: dict[str, str] = {
    "gateway_fee_line": DreLine.SELLING_EXPENSES.value,
    "anticipation_fee_line": DreLine.FINANCIAL_EXPENSES.value,
    "chargeback_line": DreLine.DEDUCTIONS.value,
    "chargeback_fee_line": DreLine.SELLING_EXPENSES.value,
    "installment_interest_line": DreLine.GROSS_REVENUE.value,
}
CHOICES: tuple[str, ...] = tuple(CHOICE_DEFAULTS)
_REAL_LINES = tuple(v for v in values(DreLine) if v != DreLine.UNCLASSIFIED.value)


def _plain(value: Any) -> Any:
    return getattr(value, "value", value)


def defaults(regime: Optional[str] = None) -> dict:
    return {
        "tax_regime": regime or TaxRegime.UNKNOWN.value,
        "das_split_irpj_csll": False,
        "das_irpj_csll_share_bps": 0,
        **CHOICE_DEFAULTS,
        "choice_meta": {},
    }


def load_row(s: Scope) -> Optional[dict]:
    return first(s.tbl("dre_settings").select("*").eq("org_id", s.org_id).limit(1).execute())


def present(row: Optional[Mapping[str, Any]], *, regime_prefill: Optional[str] = None) -> dict:
    """The API shape: scalar settings + each choice with its provisional/confirmation state."""
    base = {**defaults(regime_prefill), **{k: v for k, v in (row or {}).items() if v is not None}}
    meta = base.get("choice_meta") or {}
    choices = {}
    for name in CHOICES:
        m = meta.get(name) or {}
        choices[name] = {
            "value": base[name],
            "default": CHOICE_DEFAULTS[name],
            "provisional": bool(m.get("provisional", True)),
            "confirmed_by": m.get("confirmed_by"),
            "confirmed_at": m.get("confirmed_at"),
            "note": m.get("note"),
        }
    return {
        "persisted": row is not None,
        "tax_regime": base["tax_regime"],
        "tax_regime_prefilled": row is None and regime_prefill is not None,
        "das_split_irpj_csll": bool(base["das_split_irpj_csll"]),
        "das_irpj_csll_share_bps": int(base["das_irpj_csll_share_bps"] or 0),
        "choices": choices,
    }


def get_settings(s: Scope, *, regime_prefill: Optional[str] = None) -> dict:
    return present(load_row(s), regime_prefill=regime_prefill)


def update_settings(s: Scope, data: Mapping[str, Any], *, user_id: Optional[str] = None, regime_prefill: Optional[str] = None) -> dict:
    """Partial update (PUT). Admin-only at the router. Returns the presented settings."""
    row = load_row(s)
    current = {**defaults(regime_prefill), **(row or {})}
    meta: dict[str, dict] = {k: dict(v) for k, v in (current.get("choice_meta") or {}).items()}
    patch: dict[str, Any] = {}
    now = now_iso()

    if data.get("tax_regime") is not None:
        patch["tax_regime"] = _plain(data["tax_regime"])
    if data.get("das_split_irpj_csll") is not None:
        patch["das_split_irpj_csll"] = bool(data["das_split_irpj_csll"])
    if data.get("das_irpj_csll_share_bps") is not None:
        patch["das_irpj_csll_share_bps"] = int(data["das_irpj_csll_share_bps"])
    for name in CHOICES:
        if data.get(name) is None:
            continue
        line = _plain(data[name])
        if line not in _REAL_LINES:
            raise invalid(name, "Escolha uma linha real da DRE (não 'sem classificação').", code="linha_dre_invalida")
        if line != current[name]:
            patch[name] = line
            meta[name] = {"provisional": True, "confirmed_by": None, "confirmed_at": None, "note": None}

    for name, conf in (data.get("confirmations") or {}).items():
        if name not in CHOICES:
            raise invalid("confirmations", f"Escolha desconhecida: {name}.", code="escolha_desconhecida")
        c = conf if isinstance(conf, Mapping) else conf.model_dump()
        if c.get("confirmed"):
            meta[name] = {"provisional": False, "confirmed_by": user_id, "confirmed_at": now, "note": c.get("note")}
        else:
            meta[name] = {"provisional": True, "confirmed_by": None, "confirmed_at": None, "note": c.get("note")}
    if meta != (current.get("choice_meta") or {}):
        patch["choice_meta"] = meta

    merged = {**current, **patch}
    if merged["das_split_irpj_csll"] and int(merged["das_irpj_csll_share_bps"] or 0) <= 0:
        raise invalid(
            "das_irpj_csll_share_bps",
            "Informe o percentual de repartição do IRPJ/CSLL do seu anexo (em pontos-base) para dividir o DAS.",
            code="reparticao_das_obrigatoria",
        )
    if not patch and row is not None:
        return present(row, regime_prefill=regime_prefill)

    patch["updated_at"] = now
    patch["updated_by"] = user_id
    if row is None:
        insert = {
            **{k: v for k, v in defaults(regime_prefill).items() if k != "choice_meta"},
            "choice_meta": meta,
            **patch,
            "id": new_id(),
            "org_id": s.org_id,
            "created_at": now,
        }
        try:
            s.tbl("dre_settings").insert(insert).execute()
        except Exception as exc:
            if not is_unique_violation(exc):
                raise
            # Lost the first-PUT race: the winner's row exists, so this becomes a plain update.
            s.tbl("dre_settings").update(patch).eq("org_id", s.org_id).execute()
    else:
        s.tbl("dre_settings").update(patch).eq("org_id", s.org_id).execute()
    return present(load_row(s), regime_prefill=regime_prefill)


__all__ = ["CHOICES", "CHOICE_DEFAULTS", "defaults", "get_settings", "load_row", "present", "update_settings"]
