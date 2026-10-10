"""Segundo Cérebro's side of the shared transcription layer (cerebro-contract.md §3, §10).

Registers the ``cerebro_resposta`` context (``contexto_ref = '{brain_id}:{question_id}'``):

- ``validar``: the brain must be the caller's org's questionnaire brain and the
  question one of its template's — a recording can never be pointed at someone
  else's answer (404, same as every other foreign Cérebro id).
- ``aplicar``: routes the finished transcript into ``cs_brain_answers`` — blank
  answer -> ``text := transcript``; otherwise ``text + "\\n\\n" + transcript`` — and
  resets the AI review (the text changed). The transcription layer guarantees it
  runs exactly once per transcription.

The answer column is capped at ``MAX_ANSWER_CHARS`` (a CHECK). A transcript that
does not fit is clipped at a word boundary and LOGGED; the full text stays on the
``transcricoes`` row (and is returned as ``Answer.transcricao.texto``) for 7 days.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.modules.media_creation.schemas.cerebro import MAX_ANSWER_CHARS
from app.modules.media_creation.services.cerebro_service import ANSWERS, CerebroError, CerebroService
from app.modules.transcricoes import hooks
from app.modules.transcricoes.errors import TranscricaoErro

logger = logging.getLogger(__name__)

CONTEXTO_TIPO = "cerebro_resposta"


def parse_ref(ref: str) -> tuple[str, str]:
    """``'{brain_id}:{question_id}'`` -> ``(brain_id, question_id)``."""
    brain_id, sep, qid = (ref or "").partition(":")
    if not sep or not brain_id or not qid:
        raise TranscricaoErro("contexto_invalido", mensagem="Referência da pergunta inválida.")
    return brain_id, qid


def make_ref(brain_id: str, question_id: str) -> str:
    return f"{brain_id}:{question_id}"


def validar(db: Any, org_id: str, user_id: str, ref: str) -> None:
    brain_id, qid = parse_ref(ref)
    svc = CerebroService(db, org_id, user_id)
    try:
        _, spec = svc._require_questionnaire(brain_id)
        svc._assert_question(spec, qid)
    except CerebroError as exc:
        raise TranscricaoErro("nao_encontrada", status=exc.status, mensagem=exc.detail) from None


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    head, sep, _ = cut.rpartition(" ")
    return (head if sep and len(head) > limit * 0.8 else cut).rstrip()


def aplicar(db: Any, row: dict[str, Any]) -> None:
    brain_id, qid = parse_ref(row["contexto_ref"])
    transcript = (row.get("texto") or "").strip()
    svc = CerebroService(db, str(row["org_id"]), str(row["user_id"]))
    try:
        svc.get_brain_row(brain_id)
    except CerebroError:
        logger.warning("cerebro voz: cérebro %s não existe mais; transcrição %s não aplicada", brain_id, row["id"])
        return
    if not transcript:
        return
    existing = svc._answer_row(brain_id, qid)
    current = (existing or {}).get("text") or ""
    combined = transcript if not current.strip() else f"{current}\n\n{transcript}"
    if len(combined) > MAX_ANSWER_CHARS:
        logger.warning(
            "cerebro voz: resposta passaria de %s caracteres (transcrição %s); texto cortado na resposta, "
            "completo na transcrição", MAX_ANSWER_CHARS, row["id"],
        )
        combined = _clip(combined, MAX_ANSWER_CHARS)
    svc.put_answer(brain_id, qid, combined)  # inserts/updates + resets a stale review
    db.table(ANSWERS).update({"transcricao_id": str(row["id"])}).eq("brain_id", brain_id).eq(
        "question_id", qid
    ).eq("org_id", str(row["org_id"])).execute()


def register_contexto() -> None:
    hooks.register_contexto(CONTEXTO_TIPO, validar=validar, aplicar=aplicar)


__all__ = ["CONTEXTO_TIPO", "aplicar", "make_ref", "parse_ref", "register_contexto", "validar"]
