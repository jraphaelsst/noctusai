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
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from noctusai_lib.email.digest import (
    Digest,
    DigestSendResult,
    render as render_digest,
    send_digest,
)
from noctusai_lib.llm import chat_completion

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "email_templates"

MODEL = "gpt-4o-mini"
PROMPT_VERSION = "pf-monthly-narrative@v1"


def _fmt_brl(value: float | int | None) -> str:
    if value is None:
        return "R$ 0"
    v = float(value)
    return f"R$ {v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


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

    try:
        narrative = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=MODEL,
            temperature=0.0,
            max_tokens=600,
            cache=True,
            org_id=org_id,
        )
        return narrative.strip()
    except Exception:
        logger.warning("pf.monthly_narrative: LLM unavailable — using template fallback")
        return (
            f"Resumo automático do período {period_label}: "
            f"entradas {_fmt_brl(receita)}, saídas {_fmt_brl(despesa)}, "
            f"fluxo líquido {_fmt_brl(fluxo)} (taxa de poupança {poupanca_pct:.1f}%). "
            f"Sem narrativa detalhada — LLM indisponível para esta janela."
        )


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
    org_res = (
        db.table("organizations").select("id, nome").eq("id", org_id).single().execute()
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
    return render_digest(
        html_template="monthly_narrative.html.j2",
        text_template="monthly_narrative.txt.j2",
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
            "narrative": narrative,
            "narrative_paragraphs": [
                para for para in narrative.split("\n\n") if para.strip()
            ],
            "prompt_version": PROMPT_VERSION,
        },
        search_paths=[_TEMPLATE_DIR],
    )


async def build_narrative(
    db: Any,
    *,
    org_id: str,
    period_days: int = 30,
) -> tuple[Digest, dict[str, Any]]:
    """Compute aggregates + narrative + render bodies. No DB writes, no email send.

    Returns `(Digest, summary_dict)`. Suitable for dashboard cards or
    inspection endpoints.
    """
    transacoes, org_record = await _fetch_window(db, org_id, period_days)
    org_name = org_record.get("nome") or "Você"

    receita, despesa, by_categoria, count = _aggregate_period(transacoes)
    fluxo = receita - despesa
    poupanca_pct = (fluxo / receita * 100.0) if receita > 0 else 0.0
    top_categorias = sorted(by_categoria.items(), key=lambda x: x[1], reverse=True)

    end_date = date.today()
    start_date = end_date - timedelta(days=period_days)
    period_label = f"Últimos {period_days} dias ({start_date.isoformat()} → {end_date.isoformat()})"

    narrative = await _generate_narrative(
        period_label=period_label,
        receita=receita,
        despesa=despesa,
        fluxo=fluxo,
        poupanca_pct=poupanca_pct,
        top_categorias=top_categorias,
        transacoes_count=count,
        org_id=org_id,
    )

    html, text = _render_bodies(
        org_name=org_name,
        period_label=period_label,
        receita=receita,
        despesa=despesa,
        fluxo=fluxo,
        poupanca_pct=poupanca_pct,
        top_categorias=top_categorias,
        narrative=narrative,
    )
    digest = Digest(
        subject=f"[NoctusAI] Resumo financeiro mensal — {org_name}",
        text=text,
        html=html,
    )
    summary = {
        "period_days": period_days,
        "period_label": period_label,
        "receita_total": round(receita, 2),
        "despesa_total": round(despesa, 2),
        "fluxo_liquido": round(fluxo, 2),
        "taxa_poupanca": round(poupanca_pct, 2),
        "top_categorias": [
            {"nome": n, "total": round(t, 2)} for n, t in top_categorias[:6]
        ],
        "transacoes_count": count,
        "narrative": narrative,
    }
    return digest, summary


async def send_monthly_narrative(
    db: Any,
    *,
    org_id: str,
    recipient: str,
    period_days: int = 30,
) -> dict[str, Any]:
    """Build + send via Resend. Returns structured `DigestSendResult`-shaped dict."""
    digest, summary = await build_narrative(db, org_id=org_id, period_days=period_days)
    outcome: DigestSendResult = await send_digest(
        digest, recipient=recipient, org_id=org_id, log_prefix="PF MONTHLY"
    )
    return {
        "sent": outcome.sent,
        "dry_run": outcome.dry_run,
        "external_id": outcome.external_id,
        "error": outcome.error,
        "subject": digest.subject,
        "summary": summary,
    }
