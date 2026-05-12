"""
AI Service — multi-provider LLM features for Personal Finance.

Phase 7 P1 indicators (ai-expansion):
  • categorize_transaction  — suggest a category for a transaction (P1-opp)
  • flag_recurring_expense  — detect whether a transaction looks recurring (P3-opp)

Both call `noctusai_lib.llm.chat_completion(cache=True, org_id=...)`. The
router wraps the AIOutput-shaped dict into `noctusai_lib.ai.AIOutput(...)`
and persists via `persist_output(db, schema="personal-finance", output)`.

**Audit wiring (llm-tool-audit-rollout Phase 4).** Every `chat_completion`
dispatch writes one row to `"personal-finance".tool_call_audits` via the
seed `make_audit_writer` (best-effort — never breaks dispatch). LGPD
redaction is registered alongside each feature in
`app.services.ai_consent_features`; the `build_audit_record` helper in
`app.services.audit_hook` applies it BEFORE the row is persisted.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.llm import chat_completion
from noctusai_lib.primitives.parsing import safe_float as _safe_float

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"

PROMPT_VERSION_CATEGORIZE = "pf-categorize@v1"
PROMPT_VERSION_RECURRING = "pf-recurring@v1"


def _audit_dispatch(
    *,
    feature_key: str,
    tool_name: str,
    status: str,
    arguments: Optional[dict[str, Any]] = None,
    result: Any = None,
    error: Optional[str] = None,
    duration_ms: int = 0,
) -> None:
    """Best-effort audit-row write — never raises to the caller.

    Looks up the feature's redactors via `audit_hook.build_audit_record` and
    persists via `get_audit_writer()`. Wrapped in try/except so an audit-side
    failure cannot break the user-facing AI call (matches the seed
    `make_audit_writer` best-effort contract one level out).
    """
    try:
        from app.services.audit_hook import build_audit_record, get_audit_writer

        record = build_audit_record(
            feature_key=feature_key,
            tool_name=tool_name,
            status=status,
            duration_ms=duration_ms,
            arguments=arguments,
            result=result,
            error=error,
        )
        writer = get_audit_writer()
        writer(record)
    except Exception:
        logger.exception("pf.ai._audit_dispatch failed for feature=%s", feature_key)


def check_openai_configured(org_id: Optional[str] = None) -> bool:
    """Check if OpenAI API key is available without raising."""
    return bool(resolve_credential("openai_api_key", org_id))


def _empty_output(label: str = "indisponível") -> dict:
    return {
        "kind": "flag",
        "label": label,
        "chip": None,
        "explanation": "LLM indisponível — indicador não gerado.",
        "confidence": None,
        "score": None,
        "model_version": MODEL,
        "prompt_version": None,
    }


async def categorize_transaction(
    *,
    descricao: str,
    valor: float,
    tipo: str,
    comerciante: Optional[str] = None,
    available_categories: Optional[list[dict]] = None,
    org_id: Optional[str] = None,
) -> dict:
    """P1-opp — suggest a category for a transaction.

    Returns AIOutput-shaped dict with `kind="classification"`. The label
    is the suggested category name (free text); `chip` is an uppercase
    short tag; `metadata` (caller-side) can carry the matched category id.
    """
    if not descricao and not comerciante:
        return _empty_output("transação vazia")

    cats = available_categories or []
    if cats:
        cat_lines = "\n".join(
            f"- {c.get('nome', '?')}" + (f" ({c['tipo']})" if c.get("tipo") else "")
            for c in cats[:30]
        )
    else:
        cat_lines = "(usuário não definiu categorias — sugira uma genérica)"

    system = (
        "Você é um assistente de finanças pessoais brasileiro. Classifique "
        "a transação na MELHOR categoria disponível. Responda no formato:\n"
        "CATEGORY: <nome exato da categoria>\n"
        "CONFIDENCE: <0 a 1>\n"
        "EXPLANATION: <até 14 palavras>"
    )
    user_prompt = (
        f"Tipo: {tipo}\n"
        f"Valor: R$ {valor:.2f}\n"
        f"Descrição: {descricao or '(vazio)'}\n"
        f"Comerciante: {comerciante or '(não informado)'}\n"
        f"Categorias disponíveis:\n{cat_lines}"
    )

    _audit_args = {
        "tipo": tipo,
        "descricao": descricao,
        "comerciante": comerciante,
        "valor": valor,
        "available_categories": cats,
        "org_id": org_id,
    }
    _started = time.monotonic()
    try:
        content = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=MODEL,
            temperature=0.0,
            max_tokens=140,
            cache=True,
            org_id=org_id,
        )
    except Exception as _exc:
        logger.warning("pf.ai.categorize_transaction: LLM unavailable")
        _audit_dispatch(
            feature_key="pf.transaction_categorize",
            tool_name="pf.transaction_categorize",
            status="failure",
            arguments=_audit_args,
            result=None,
            error=str(_exc),
            duration_ms=int((time.monotonic() - _started) * 1000),
        )
        return _empty_output()

    category = ""
    confidence: Optional[float] = None
    explanation = ""
    for line in content.splitlines():
        s = line.strip()
        u = s.upper()
        if u.startswith("CATEGORY:") or u.startswith("CATEGORIA:"):
            category = s.split(":", 1)[1].strip()
        elif u.startswith("CONFIDENCE:"):
            confidence = max(0.0, min(1.0, _safe_float(s.split(":", 1)[1], 0.5)))
        elif u.startswith("EXPLANATION:"):
            explanation = s.split(":", 1)[1].strip()

    if not category:
        category = "Outros"

    matched_cat: Optional[dict[str, Any]] = None
    if cats:
        target = category.lower()
        matched_cat = next(
            (c for c in cats if (c.get("nome") or "").lower() == target),
            None,
        )

    chip = (category[:18]).upper() if category else None

    _out = {
        "kind": "classification",
        "label": category,
        "chip": chip,
        "explanation": explanation or None,
        "confidence": confidence,
        "score": None,
        "model_version": MODEL,
        "prompt_version": PROMPT_VERSION_CATEGORIZE,
        "matched_categoria_id": matched_cat["id"] if matched_cat else None,
    }
    _audit_dispatch(
        feature_key="pf.transaction_categorize",
        tool_name="pf.transaction_categorize",
        status="success",
        arguments=_audit_args,
        result=_out,
        duration_ms=int((time.monotonic() - _started) * 1000),
    )
    return _out


async def flag_recurring_expense(
    *,
    descricao: str,
    valor: float,
    tipo: str,
    similar_history: Optional[list[dict]] = None,
    org_id: Optional[str] = None,
) -> dict:
    """P3-opp — detect whether a transaction looks like a recurring expense.

    `similar_history` is a list of `{data, valor, descricao}` dicts of
    transactions that share a comerciante/descricao prefix. Returns an
    AIOutput-shaped dict with `kind="flag"` (label = `recorrente` |
    `pontual` | `incerto`) and `score` 0-1 (probability recurring).
    """
    if not descricao:
        return _empty_output("transação sem descrição")

    history = similar_history or []
    history_lines = "\n".join(
        f"- {h.get('data', '?')}: R$ {h.get('valor', 0):.2f} — {h.get('descricao', '')}"
        for h in history[:12]
    ) or "(sem histórico similar registrado)"

    system = (
        "Você é um assistente de finanças pessoais. Decida se a transação "
        "abaixo é parte de um padrão RECORRENTE (mensalidade, assinatura, "
        "salário, fatura fixa). Use o histórico fornecido para julgar. "
        "Responda no formato:\n"
        "FLAG: recorrente | pontual | incerto\n"
        "PROBABILITY: <0 a 1>\n"
        "EXPLANATION: <até 16 palavras>"
    )
    user_prompt = (
        f"Tipo: {tipo}\n"
        f"Valor: R$ {valor:.2f}\n"
        f"Descrição: {descricao}\n"
        f"Histórico similar (mais recentes primeiro):\n{history_lines}"
    )

    _audit_args = {
        "tipo": tipo,
        "descricao": descricao,
        "valor": valor,
        "similar_history": history,
        "org_id": org_id,
    }
    _started = time.monotonic()
    try:
        content = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=MODEL,
            temperature=0.0,
            max_tokens=140,
            cache=True,
            org_id=org_id,
        )
    except Exception as _exc:
        logger.warning("pf.ai.flag_recurring_expense: LLM unavailable")
        _audit_dispatch(
            feature_key="pf.recurring_flag",
            tool_name="pf.recurring_flag",
            status="failure",
            arguments=_audit_args,
            result=None,
            error=str(_exc),
            duration_ms=int((time.monotonic() - _started) * 1000),
        )
        return _empty_output()

    flag = "incerto"
    probability = 0.5
    explanation = ""
    for line in content.splitlines():
        s = line.strip()
        u = s.upper()
        if u.startswith("FLAG:"):
            raw = s.split(":", 1)[1].strip().lower()
            if "recorr" in raw:
                flag = "recorrente"
            elif "pontual" in raw:
                flag = "pontual"
            else:
                flag = "incerto"
        elif u.startswith("PROBABILITY:") or u.startswith("PROB:"):
            probability = max(0.0, min(1.0, _safe_float(s.split(":", 1)[1], 0.5)))
        elif u.startswith("EXPLANATION:"):
            explanation = s.split(":", 1)[1].strip()

    chip_map = {"recorrente": "RECORRENTE", "pontual": "PONTUAL", "incerto": "INCERTO"}

    _out = {
        "kind": "flag",
        "label": flag,
        "score": probability,
        "chip": chip_map[flag],
        "explanation": explanation or None,
        "confidence": probability,
        "model_version": MODEL,
        "prompt_version": PROMPT_VERSION_RECURRING,
    }
    _audit_dispatch(
        feature_key="pf.recurring_flag",
        tool_name="pf.recurring_flag",
        status="success",
        arguments=_audit_args,
        result=_out,
        duration_ms=int((time.monotonic() - _started) * 1000),
    )
    return _out
