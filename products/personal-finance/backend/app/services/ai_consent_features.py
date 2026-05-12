"""Personal Finance AI consent features — registered at app boot.

Per `consent-guard-rollout` Phase 5 (2026-04-27). 3 features:
  - 2 medium-risk (transaction descriptions in prompt) → `default_granted=True`
    (preserves current product behavior; users still see in /api/me/consents).
  - 1 high-risk (personal financial narrative) → `default_granted=False`
    (opt-in only; matches Daily Life weekly_review posture).

Imported once by `app.main` so its `register_feature(...)` calls populate
the platform-wide consent catalog at boot.

**LGPD redaction (Phase 4 / llm-tool-audit-rollout).** Every `register_feature`
call wires `redact_arguments` + `redact_result` callables. PF is
finance-LGPD sensitive — transaction descriptions (`descricao` / `comerciante`),
account balances, and income figures (raw values + aggregated receita / despesa
/ fluxo) are scrubbed BEFORE the row lands in `tool_call_audits`. The audit
table keeps only structural metadata (counts, category names, confidence
scores, prompt versions) — never the free-text personal narrative.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.domain.ai import register_feature

# ---------------------------------------------------------------------------
# Redaction helpers — module-private. Each takes the raw arguments / result
# dict and returns a JSON-friendly dict containing ONLY structural metadata.
# When the input is None we return None; any unexpected shape over-redacts
# (drops to None) — over-redaction is the safe default for finance PII.
# ---------------------------------------------------------------------------

_SENSITIVE_FREEFORM_KEYS = {"descricao", "comerciante", "narrative", "content"}
_SENSITIVE_NUMERIC_KEYS = {
    "valor",
    "receita",
    "despesa",
    "fluxo",
    "saldo",
    "balance",
    "income",
    "amount",
    "total",
    "receita_total",
    "despesa_total",
    "fluxo_liquido",
}


def _scrub_value(value: Any) -> Any:
    """Drop sensitive free-form text + numeric amounts; keep keys structural."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for k, v in value.items():
            key_lower = str(k).lower()
            if key_lower in _SENSITIVE_FREEFORM_KEYS:
                cleaned[k] = "[redacted]"
            elif key_lower in _SENSITIVE_NUMERIC_KEYS:
                cleaned[k] = "[redacted]"
            else:
                cleaned[k] = _scrub_value(v)
        return cleaned
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    return value


def _redact_categorize_arguments(arguments: Any) -> dict[str, Any]:
    """`categorize_transaction` arguments → keep tipo + category-count + length
    metadata; drop descricao / comerciante / valor (raw transaction text + amount).
    """
    if not isinstance(arguments, dict):
        return {}
    cats = arguments.get("available_categories") or []
    return {
        "tipo": arguments.get("tipo"),
        "has_descricao": bool(arguments.get("descricao")),
        "has_comerciante": bool(arguments.get("comerciante")),
        "available_category_count": len(cats) if isinstance(cats, list) else None,
        "org_id": arguments.get("org_id"),
    }


def _redact_categorize_result(result: Any) -> Any:
    """`categorize_transaction` result → keep classification metadata only."""
    if not isinstance(result, dict):
        return None
    return {
        "kind": result.get("kind"),
        "label": result.get("label"),  # category name — NOT user free-text
        "chip": result.get("chip"),
        "confidence": result.get("confidence"),
        "score": result.get("score"),
        "model_version": result.get("model_version"),
        "prompt_version": result.get("prompt_version"),
        "matched_categoria_id": result.get("matched_categoria_id"),
    }


def _redact_recurring_arguments(arguments: Any) -> dict[str, Any]:
    """`flag_recurring_expense` arguments → keep tipo + history-count;
    drop descricao + valor + similar_history (per-row descricao/valor leak)."""
    if not isinstance(arguments, dict):
        return {}
    history = arguments.get("similar_history") or []
    return {
        "tipo": arguments.get("tipo"),
        "has_descricao": bool(arguments.get("descricao")),
        "similar_history_count": len(history) if isinstance(history, list) else None,
        "org_id": arguments.get("org_id"),
    }


def _redact_recurring_result(result: Any) -> Any:
    """`flag_recurring_expense` result → keep flag + score + chip; drop explanation."""
    if not isinstance(result, dict):
        return None
    return {
        "kind": result.get("kind"),
        "label": result.get("label"),  # recorrente / pontual / incerto
        "chip": result.get("chip"),
        "score": result.get("score"),
        "confidence": result.get("confidence"),
        "model_version": result.get("model_version"),
        "prompt_version": result.get("prompt_version"),
    }


def _redact_monthly_narrative_arguments(arguments: Any) -> dict[str, Any]:
    """`monthly_narrative` arguments → keep period + transaction-count +
    category-count; drop ALL amounts (receita / despesa / fluxo) AND the
    narrative-shaped fields (top categoria total values, period totals).
    """
    if not isinstance(arguments, dict):
        return {}
    top_categorias = arguments.get("top_categorias") or []
    return {
        "period_label": arguments.get("period_label"),
        "period_days": arguments.get("period_days"),
        "transacoes_count": arguments.get("transacoes_count"),
        "top_categoria_names": [
            (item.get("nome") if isinstance(item, dict) else None)
            for item in top_categorias
        ] if isinstance(top_categorias, list) else [],
        "top_categoria_count": (
            len(top_categorias) if isinstance(top_categorias, list) else None
        ),
        "org_id": arguments.get("org_id"),
    }


def _redact_monthly_narrative_result(result: Any) -> Any:
    """`monthly_narrative` result → DROP entirely. The 3-paragraph narrative
    is personal financial story; even structural metadata (sentence count,
    char length) leaks behavioral signal. Keep only model identifier."""
    if isinstance(result, dict):
        return {
            "model_version": result.get("model_version"),
            "prompt_version": result.get("prompt_version"),
        }
    if isinstance(result, str):
        # The narrative text itself — fully drop, keep only length signal-class.
        return {"narrative_length_class": "non-empty" if result else "empty"}
    return None


# ---------------------------------------------------------------------------
# Registrations
# ---------------------------------------------------------------------------

# P1-opp — Transaction auto-categorization (medium-risk: transaction
# description / merchant text in prompt — but org-internal, not personal narrative)
register_feature(
    "pf.transaction_categorize",
    title="Categorização de transações por IA",
    rationale=(
        "A IA sugere uma categoria para uma transação a partir de sua "
        "descrição, comerciante e valor. Esses dados transitam pelo "
        "provedor LLM. A sugestão respeita as categorias já cadastradas "
        "na sua organização."
    ),
    product="personal-finance",
    default_granted=True,
    redact_arguments=_redact_categorize_arguments,
    redact_result=_redact_categorize_result,
)

# P3-opp — Recurring expense flag (medium-risk: same shape as P1-opp but with
# 12 months of same-merchant history)
register_feature(
    "pf.recurring_flag",
    title="Detecção de despesas recorrentes",
    rationale=(
        "A IA analisa até 12 meses de transações do mesmo comerciante "
        "para sinalizar gastos potencialmente recorrentes (assinaturas, "
        "contas, mensalidades). Os dados das transações transitam pelo "
        "provedor LLM."
    ),
    product="personal-finance",
    default_granted=True,
    redact_arguments=_redact_recurring_arguments,
    redact_result=_redact_recurring_result,
)

# P2-opp — Monthly narrative (HIGH-RISK: personal financial story, 30 days
# of receita/despesa/fluxo aggregated + top categorias context)
register_feature(
    "pf.monthly_narrative",
    title="Narrativa financeira mensal",
    rationale=(
        "A IA gera uma narrativa em 3 parágrafos sobre suas finanças do "
        "mês — receita, despesa, fluxo líquido, taxa de poupança e top "
        "categorias. A narrativa é uma história pessoal sobre seu dinheiro; "
        "os dados financeiros transitam pelo provedor LLM. Opt-in: ative "
        "manualmente para receber o resumo mensal."
    ),
    product="personal-finance",
    default_granted=False,
    redact_arguments=_redact_monthly_narrative_arguments,
    redact_result=_redact_monthly_narrative_result,
)
