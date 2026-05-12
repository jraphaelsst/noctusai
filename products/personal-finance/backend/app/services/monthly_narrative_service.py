"""
PF P2-opp — monthly financial narrative (ai-expansion Phase 10).

Aggregates the past 30 days of transactions for an org → income vs.
spending breakdowns + top categories + savings rate → asks the LLM for a
3-paragraph PT narrative (overview + observations + tip) → renders html
+ text via inline f-strings (Jinja migration is a separate cross-cutting
project — see KB § 04-SHARED-LIBRARY § email/) → optionally fans out via
`noctusai_lib.email.digest.send_digest` to a configured recipient email.

Two entry points:
  - `build_narrative(db, org_id)` — pure compute. Returns a Digest +
    summary dict. Used by the dashboard card endpoint.
  - `send_monthly_narrative(db, org_id, recipient)` — same plus delivery.

LGPD posture: amounts + category names enter the prompt; comerciante is
intentionally NOT included (some users would consider their merchant
history personal). `cache=True` is OK at `temperature=0` because identical
aggregates produce identical narratives.
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from noctusai_lib.domain.digest import (
    BaseDigestService,
    DigestResult,
    DigestWindow,
    build_and_send,
    email_template_dir,
    narrative as digest_narrative,
    render_digest_pair,
)
from noctusai_lib.integrations.email.digest import Digest
from noctusai_lib.primitives.parsing import format_brl

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = email_template_dir(__file__)

MODEL = "gpt-4o-mini"
PROMPT_VERSION = "pf-monthly-narrative@v1"


def _fmt_brl(value: float | int | None) -> str:
    """Thin alias of `noctusai_lib.parsing.format_brl(..., decimals=2)`.

    PF monthly narratives include centavos (e.g. "R$ 1.234,56") because
    transaction amounts already carry 2-decimal precision; users would
    notice rounding.
    """
    return format_brl(value, decimals=2)


# accept-with-rationale: Per-product `_render_bodies` + `_generate_narrative` digest wrappers retained at N=4 in KB § PATTERNS/accept-with-rationale.md
async def _generate_narrative(
    *,
    period_label: str,
    receita: float,
    despesa: float,
    fluxo: float,
    poupanca_pct: float,
    top_categorias: list[tuple[str, float]],
    transacoes_count: int,
    org_id: Optional[str],
) -> str:
    bullets = "\n".join(
        f"- {nome}: {_fmt_brl(total)}" for nome, total in top_categorias[:6]
    ) or "- (sem categorias)"

    system = (
        "Você é um assistente de finanças pessoais brasileiro. Resuma o "
        "mês em três parágrafos curtos: (1) panorama geral (entradas, "
        "saídas, fluxo, taxa de poupança), (2) observações sobre as "
        "categorias de maior gasto, (3) UMA dica acionável e específica "
        "para o próximo mês. Use português do Brasil, tom direto e "
        "amigável, sem clichês motivacionais e sem emojis. Não invente "
        "números além dos fornecidos."
    )
    user_prompt = (
        f"Período: {period_label}\n"
        f"Receita total: {_fmt_brl(receita)}\n"
        f"Despesa total: {_fmt_brl(despesa)}\n"
        f"Fluxo líquido: {_fmt_brl(fluxo)}\n"
        f"Taxa de poupança: {poupanca_pct:.1f}%\n"
        f"Total de transações: {transacoes_count}\n"
        f"Top categorias de despesa:\n{bullets}"
    )

    fallback = (
        f"Resumo automático do período {period_label}: "
        f"entradas {_fmt_brl(receita)}, saídas {_fmt_brl(despesa)}, "
        f"fluxo líquido {_fmt_brl(fluxo)} (taxa de poupança {poupanca_pct:.1f}%). "
        f"Sem narrativa detalhada — LLM indisponível para esta janela."
    )
    _audit_args = {
        "period_label": period_label,
        "receita": receita,
        "despesa": despesa,
        "fluxo": fluxo,
        "poupanca_pct": poupanca_pct,
        "top_categorias": [
            {"nome": nome, "total": total} for nome, total in top_categorias[:6]
        ],
        "transacoes_count": transacoes_count,
        "org_id": org_id,
    }
    _started = time.monotonic()
    try:
        result = await digest_narrative(
            system=system,
            user_prompt=user_prompt,
            model=MODEL,
            cache=True,
            org_id=org_id,
            fallback=fallback,
        )
    except Exception as _exc:
        _audit_narrative_dispatch(
            status="failure",
            arguments=_audit_args,
            result=None,
            error=str(_exc),
            duration_ms=int((time.monotonic() - _started) * 1000),
        )
        raise
    _audit_narrative_dispatch(
        status="success",
        arguments=_audit_args,
        result=result,
        duration_ms=int((time.monotonic() - _started) * 1000),
    )
    return result


def _audit_narrative_dispatch(
    *,
    status: str,
    arguments: Optional[dict[str, Any]] = None,
    result: Any = None,
    error: Optional[str] = None,
    duration_ms: int = 0,
) -> None:
    """Best-effort audit-row write for the monthly narrative LLM call.

    Wraps `audit_hook.build_audit_record` + `get_audit_writer()` in
    try/except so an audit-side failure never breaks digest rendering.
    Redaction is applied by `build_audit_record` via the feature's
    registered `redact_arguments` / `redact_result` callables in
    `app.services.ai_consent_features`.
    """
    try:
        from app.services.audit_hook import build_audit_record, get_audit_writer

        record = build_audit_record(
            feature_key="pf.monthly_narrative",
            tool_name="pf.monthly_narrative",
            status=status,
            duration_ms=duration_ms,
            arguments=arguments,
            result=result,
            error=error,
        )
        writer = get_audit_writer()
        writer(record)
    except Exception:
        logger.exception("pf.monthly_narrative: audit dispatch failed")


def _aggregate_period(
    transacoes: list[dict],
) -> tuple[float, float, dict[str, float], int]:
    """Return (receita, despesa, totals_by_categoria, transacoes_count)."""
    receita = 0.0
    despesa = 0.0
    by_categoria: Counter = Counter()
    for tx in transacoes:
        valor = float(tx.get("valor") or 0)
        tipo = tx.get("tipo")
        if tipo == "receita":
            receita += valor
        elif tipo == "despesa":
            despesa += valor
            cat_name = (tx.get("categoria") or {}).get("nome") or "Sem categoria"
            by_categoria[cat_name] += valor
    return receita, despesa, dict(by_categoria), len(transacoes)


async def _fetch_window(
    db: Any, org_id: str, period_days: int
) -> tuple[list[dict], dict[str, Any]]:
    """Pull transactions + org metadata for the past `period_days`."""
    cutoff = (date.today() - timedelta(days=period_days)).isoformat()
    tx_res = (
        db.table("transacoes")
        .select(
            "id, data, valor, tipo, descricao, "
            "categoria:categorias(id, nome)"
        )
        .eq("org_id", org_id)
        .gte("data", cutoff)
        .order("data", desc=True)
        .limit(2000)
        .execute()
    )
    transacoes = tx_res.data or []
    # PF-8: organizations lives in the `public` schema, not the `personal-finance`
    # product schema. The `db` arg points at the product schema, so we cross-schema
    # via get_core_client() (schema="public"). Without this, PostgREST raises
    # PGRST205 ("relation organizations not found in schema personal-finance").
    from app.database import get_core_client
    core = get_core_client()
    org_res = (
        core.table("organizations").select("id, nome").eq("id", org_id).single().execute()
    )
    org_record = org_res.data or {"id": org_id, "nome": "Você"}
    return transacoes, org_record


def _render_bodies(
    *,
    org_name: str,
    period_label: str,
    receita: float,
    despesa: float,
    fluxo: float,
    poupanca_pct: float,
    top_categorias: list[tuple[str, float]],
    narrative: str,
) -> tuple[str, str]:
    return render_digest_pair(
        "monthly_narrative",
        narrative=narrative,
        context={
            "org_name": org_name,
            "period_label": period_label,
            "receita_brl": _fmt_brl(receita),
            "despesa_brl": _fmt_brl(despesa),
            "fluxo_brl": _fmt_brl(fluxo),
            "poupanca_pct": poupanca_pct,
            "top_categorias": [
                {"nome": nome, "total_brl": _fmt_brl(total)}
                for nome, total in top_categorias[:6]
            ],
        },
        search_paths=[_TEMPLATE_DIR],
        prompt_version=PROMPT_VERSION,
    )


class MonthlyNarrativeService(BaseDigestService):
    """`BaseDigestService` subclass for the PF monthly narrative.

    Methods delegate to the module-level free-functions
    (`_fetch_window`, `_aggregate_period`, `_generate_narrative`,
    `_render_bodies`) so existing test imports continue to target a
    single source of truth. The class adds the orchestration shape on
    top — the per-step logic remains module-level.
    """

    async def _fetch_window(self, window: DigestWindow):
        # `period_days` lives on the window envelope; org_id on self.
        period_days = window.period_days or 30
        transacoes, org_record = await _fetch_window(
            self.client, self.org_id or "", period_days
        )
        return {
            "transacoes": transacoes,
            "org_record": org_record,
            "period_days": period_days,
        }

    def _aggregate(self, raw):
        receita, despesa, by_categoria, count = _aggregate_period(
            raw["transacoes"]
        )
        fluxo = receita - despesa
        poupanca_pct = (fluxo / receita * 100.0) if receita > 0 else 0.0
        top_categorias = sorted(
            by_categoria.items(), key=lambda x: x[1], reverse=True
        )
        period_days = raw["period_days"]
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)
        period_label = (
            f"Últimos {period_days} dias "
            f"({start_date.isoformat()} → {end_date.isoformat()})"
        )
        org_name = raw["org_record"].get("nome") or "Você"
        return {
            "org_name": org_name,
            "period_days": period_days,
            "period_label": period_label,
            "receita": receita,
            "despesa": despesa,
            "fluxo": fluxo,
            "poupanca_pct": poupanca_pct,
            "top_categorias": top_categorias,
            "transacoes_count": count,
        }

    async def _generate_narrative(self, agg, window):
        return await _generate_narrative(
            period_label=agg["period_label"],
            receita=agg["receita"],
            despesa=agg["despesa"],
            fluxo=agg["fluxo"],
            poupanca_pct=agg["poupanca_pct"],
            top_categorias=agg["top_categorias"],
            transacoes_count=agg["transacoes_count"],
            org_id=self.org_id,
        )

    def _render_bodies(self, agg, narrative):
        return _render_bodies(
            org_name=agg["org_name"],
            period_label=agg["period_label"],
            receita=agg["receita"],
            despesa=agg["despesa"],
            fluxo=agg["fluxo"],
            poupanca_pct=agg["poupanca_pct"],
            top_categorias=agg["top_categorias"],
            narrative=narrative,
        )

    def _build_subject(self, agg, window):
        return f"[NoctusAI] Resumo financeiro mensal — {agg['org_name']}"

    def _build_summary(self, agg, narrative, window):
        return {
            "period_days": agg["period_days"],
            "period_label": agg["period_label"],
            "receita_total": round(agg["receita"], 2),
            "despesa_total": round(agg["despesa"], 2),
            "fluxo_liquido": round(agg["fluxo"], 2),
            "taxa_poupanca": round(agg["poupanca_pct"], 2),
            "top_categorias": [
                {"nome": n, "total": round(t, 2)}
                for n, t in agg["top_categorias"][:6]
            ],
            "transacoes_count": agg["transacoes_count"],
            "narrative": narrative,
        }


async def build_narrative(
    db: Any,
    *,
    org_id: str,
    period_days: int = 30,
) -> tuple[Digest, dict[str, Any]]:
    """Compute aggregates + narrative + render bodies. No DB writes, no email send.

    Returns `(Digest, summary_dict)`. Suitable for dashboard cards or
    inspection endpoints. Public API unchanged after the
    `seed-digest-base-class` refactor — internally now delegates to
    `MonthlyNarrativeService.run(...)`.
    """
    svc = MonthlyNarrativeService(client=db, org_id=org_id)
    result: DigestResult = await svc.run(
        DigestWindow(org_id=org_id, period_days=period_days)
    )
    return result.digest, result.summary


async def send_monthly_narrative(
    db: Any,
    *,
    org_id: str,
    recipient: str,
    period_days: int = 30,
) -> dict[str, Any]:
    """Build + send via Resend. Returns structured `DigestSendResult`-shaped dict."""
    digest, summary = await build_narrative(db, org_id=org_id, period_days=period_days)
    result = await build_and_send(
        digest, recipient=recipient, org_id=org_id, log_prefix="PF MONTHLY"
    )
    return {**result, "summary": summary}
