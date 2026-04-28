"""Daily Life AI wrappers — extract-tasks-from-note (D4 from ai-expansion Phase 16).

Thin `chat_completion` wrapper for the Note detail view. The user clicks
"Extrair tarefas" on a long note; the service returns a list of `{title, due_hint?}`
suggestions for the user to review + accept before they become real task rows.

The service never creates task records directly — that's the user's decision.
LGPD: notes are user-authored content but may be personal (e.g., journal
entries); `cache=False` so note text doesn't hash into a shared cache key.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from noctusai_lib.llm import chat_completion
from noctusai_lib.llm.exceptions import LLMNotConfigured

logger = logging.getLogger(__name__)

PROMPT_VERSION_EXTRACT_TASKS = "daily-life-extract-tasks@v1"


def _safe_json_loads(raw: str):
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```", 2)[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip().rstrip("`").strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


_EXTRACT_SYSTEM = """Você é um assistente de produtividade em português.
Analise a nota do usuário e extraia itens acionáveis — coisas que o usuário
precisa FAZER. Ignore: reflexões, histórico, conversas passadas, sentimentos.

Para cada item:
- "title": frase curta no infinitivo (ex: "Comprar leite", "Ligar para João", "Revisar proposta")
- "due_hint": opcional, se a nota mencionar prazo ("amanhã", "sexta-feira", "próxima semana"); senão null

Responda SOMENTE JSON válido no formato:
{"tasks": [{"title": "...", "due_hint": "..." | null}, ...]}

Máximo 10 tarefas. Se a nota não tiver itens acionáveis, retorne {"tasks": []}."""


async def extract_tasks_from_note(
    note_content: str, *, org_id: Optional[str] = None
) -> list[dict]:
    """Extract actionable tasks from a user note.

    Returns `[{"title": str, "due_hint": str|None}, ...]`. Empty list on
    LLM-not-configured (UI falls back to manual task creation).
    """
    if not note_content or not note_content.strip():
        return []
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
    except (LLMNotConfigured, RuntimeError):
        logger.warning("daily_life.ai.extract_tasks: LLM unavailable — returning empty list")
        return []
    parsed = _safe_json_loads(raw)
    if not isinstance(parsed, dict):
        return []
    tasks = parsed.get("tasks")
    if not isinstance(tasks, list):
        return []
    return [
        {
            "title": str(t.get("title", "")).strip(),
            "due_hint": (t.get("due_hint") if t.get("due_hint") else None),
        }
        for t in tasks
        if isinstance(t, dict) and t.get("title")
    ][:10]


__all__ = ["PROMPT_VERSION_EXTRACT_TASKS", "extract_tasks_from_note"]
