"""Daily Life AI wrappers — extract-tasks-from-note (D4 from ai-expansion Phase 16).

Thin `chat_completion` wrapper for the Note detail view. The user clicks
"Extrair tarefas" on a long note; the service returns a list of `{title, due_hint?}`
suggestions for the user to review + accept before they become real task rows.

The service never creates task records directly — that's the user's decision.
LGPD: notes are user-authored content but may be personal (e.g., journal
entries); `cache=False` so note text doesn't hash into a shared cache key.

**Audit-trail wiring** (`llm-tool-audit-rollout` Phase 4 — Engineer LLM-DL).
Every successful or failed dispatch writes a row to
`daily_life.tool_call_audits` via `app.services.audit_hook.get_audit_writer()`.
The `daily_life.note_extract` consent feature carries the redaction lambdas
that scrub note body + extracted titles BEFORE the AuditRecord is built.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from noctusai_lib.integrations.llm import chat_completion
from noctusai_lib.integrations.llm.exceptions import LLMNotConfigured
from noctusai_lib.primitives.parsing import safe_json_loads as _safe_json_loads

logger = logging.getLogger(__name__)

PROMPT_VERSION_EXTRACT_TASKS = "daily-life-extract-tasks@v1"

# Tool / consent-feature identifiers — exposed for tests + audit-row joins.
TOOL_NAME_EXTRACT_TASKS = "daily_life.extract_tasks_from_note"
FEATURE_KEY_NOTE_EXTRACT = "daily_life.note_extract"


_EXTRACT_SYSTEM = """Você é um assistente de produtividade em português.
Analise a nota do usuário e extraia itens acionáveis — coisas que o usuário
precisa FAZER. Ignore: reflexões, histórico, conversas passadas, sentimentos.

Para cada item:
- "title": frase curta no infinitivo (ex: "Comprar leite", "Ligar para João", "Revisar proposta")
- "due_hint": opcional, se a nota mencionar prazo ("amanhã", "sexta-feira", "próxima semana"); senão null

Responda SOMENTE JSON válido no formato:
{"tasks": [{"title": "...", "due_hint": "..." | null}, ...]}

Máximo 10 tarefas. Se a nota não tiver itens acionáveis, retorne {"tasks": []}."""


def _write_audit(
    *,
    arguments: dict,
    result,
    status: str,
    duration_ms: int,
    error: Optional[str] = None,
) -> None:
    """Best-effort audit-row write. Imports are lazy so a missing audit
    surface (e.g. tests without the SQLAlchemy stack loaded) never breaks
    the user-facing dispatch."""
    try:
        from app.services.audit_hook import build_audit_record, get_audit_writer

        writer = get_audit_writer()
        record = build_audit_record(
            feature_key=FEATURE_KEY_NOTE_EXTRACT,
            tool_name=TOOL_NAME_EXTRACT_TASKS,
            status=status,
            duration_ms=duration_ms,
            arguments=arguments,
            result=result,
            error=error,
        )
        writer(record)
    except Exception:  # noqa: BLE001 — audit is best-effort by contract
        logger.exception(
            "daily_life.ai.extract_tasks: audit-row write failed (best-effort, "
            "tool dispatch unaffected)"
        )


async def extract_tasks_from_note(
    note_content: str, *, org_id: Optional[str] = None
) -> list[dict]:
    """Extract actionable tasks from a user note.

    Returns `[{"title": str, "due_hint": str|None}, ...]`. Empty list on
    LLM-not-configured (UI falls back to manual task creation).
    """
    if not note_content or not note_content.strip():
        return []
    audit_args = {
        "note_content": note_content,
        "org_id": org_id,
        "prompt_version": PROMPT_VERSION_EXTRACT_TASKS,
    }
    started = time.monotonic()
    try:
        raw = await chat_completion(
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": f"Nota:\n{note_content}"},
            ],
            temperature=0.0,
            # cache=False — note text may be personal; don't hash into cache key
            cache=False,
            org_id=org_id,
        )
    except (LLMNotConfigured, RuntimeError) as exc:
        logger.warning("daily_life.ai.extract_tasks: LLM unavailable — returning empty list")
        _write_audit(
            arguments=audit_args,
            result=None,
            status="failure",
            duration_ms=int((time.monotonic() - started) * 1000),
            error=type(exc).__name__,
        )
        return []
    parsed = _safe_json_loads(raw)
    if not isinstance(parsed, dict):
        _write_audit(
            arguments=audit_args,
            result=[],
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return []
    tasks = parsed.get("tasks")
    if not isinstance(tasks, list):
        _write_audit(
            arguments=audit_args,
            result=[],
            status="success",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return []
    result = [
        {
            "title": str(t.get("title", "")).strip(),
            "due_hint": (t.get("due_hint") if t.get("due_hint") else None),
        }
        for t in tasks
        if isinstance(t, dict) and t.get("title")
    ][:10]
    _write_audit(
        arguments=audit_args,
        result=result,
        status="success",
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return result


__all__ = [
    "FEATURE_KEY_NOTE_EXTRACT",
    "PROMPT_VERSION_EXTRACT_TASKS",
    "TOOL_NAME_EXTRACT_TASKS",
    "extract_tasks_from_note",
]
