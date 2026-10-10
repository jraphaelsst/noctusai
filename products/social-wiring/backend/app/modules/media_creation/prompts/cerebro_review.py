"""Segundo Cérebro — AI answer review prompt + output parser.

DRAFT — awaiting owner validation.

CoreStudio validated every answer and BLOCKED synthesis until all were
approved; here the review is advisory (cerebro-contract.md §1/§5): per answer
the model suggests a verdict (``approved`` / ``rejected``), a one-sentence
reason and, when it can, an improved answer. The user accepts or dismisses; the
synthesis is never gated on the review.

One call per request: the input is the template name plus every
``{question_id, question, hint, optional, answer}``; the output is a strict
JSON array ``[{question_id, verdict, reason, improved|null}]``.

Parser contract (cerebro-contract.md §5): unknown ids are ignored; an id the
model skipped is reported in ``missing`` (the service marks that answer
``error`` "A IA não avaliou esta resposta."); a reply that is not a JSON array
raises :class:`ReviewParseError` (the service marks every pending answer of the
request ``error`` "Falha ao revisar com IA"). Nothing is guessed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.modules.media_creation.schemas.cerebro import MAX_ANSWER_CHARS

MAX_REASON_CHARS = 1_000

CEREBRO_REVIEW_SYSTEM_PROMPT = """Você é um revisor de respostas de um questionário que alimenta o "segundo cérebro" de um especialista (a base de conhecimento usada depois para criar headlines e roteiros de conteúdo).
Sua função: avaliar cada resposta recebida e devolver APENAS um array JSON. Nada mais.

Para cada item de entrada você recebe: question_id, a pergunta, uma dica opcional, se a pergunta é opcional e a resposta do especialista.

Critérios — uma resposta é "approved" quando:
- responde de fato à pergunta feita (não foge do assunto);
- é concreta e específica, não genérica (nomes, situações, exemplos, números que o PRÓPRIO especialista deu);
- está na voz do especialista (primeira pessoa, linguagem dele);
- tem tamanho suficiente para ser útil (uma frase solta raramente basta, salvo quando a pergunta pede um nome ou termo);
- se a pergunta é opcional e o especialista disse que ainda não tem / não se aplica ("Ainda não"), isso é "approved".
Caso contrário, "rejected".

Regras ABSOLUTAS:
- A resposta é SOMENTE um array JSON, sem texto antes ou depois, sem markdown, sem cercas de código.
- Um objeto por question_id recebido, exatamente uma vez, no formato:
  {"question_id": "<id recebido>", "verdict": "approved" | "rejected", "reason": "<uma frase curta em português explicando o veredito>", "improved": "<resposta melhorada>" | null}
- "reason" tem no máximo uma frase curta, dirigida ao especialista ("Conte um exemplo concreto…").
- "improved" é uma versão melhor da MESMA resposta (mais clara, mais concreta, mesma voz). NUNCA invente fatos, números, nomes, histórias ou resultados que o especialista não deu. Se não for possível melhorar sem inventar, use null.
- Quando o veredito for "approved" e não houver melhoria clara, use "improved": null.
- Nunca altere os nomes próprios cunhados pelo especialista (nome do público, do inimigo, do método, de si mesmo).
- Nunca inclua question_id que não foi recebido."""


@dataclass(frozen=True)
class ReviewItem:
    question_id: str
    question: str
    hint: Optional[str]
    optional: bool
    answer: str


@dataclass(frozen=True)
class ReviewResult:
    question_id: str
    verdict: str  # approved | rejected
    reason: str
    improved: Optional[str]


@dataclass
class ParsedReview:
    results: dict[str, ReviewResult] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


class ReviewParseError(ValueError):
    """The model reply is not a usable JSON array."""


def build_review_user_message(template_name: str, items: list[ReviewItem]) -> str:
    payload = [
        {
            "question_id": it.question_id,
            "question": it.question,
            "hint": it.hint,
            "optional": it.optional,
            "answer": it.answer,
        }
        for it in items
    ]
    return (
        f"Questionário: {template_name}\n\nRespostas a revisar (JSON):\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _extract_array(raw: str) -> list[Any]:
    text = _FENCE.sub("", (raw or "").strip()).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            raise ReviewParseError("a resposta da IA não é um array JSON") from None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ReviewParseError("a resposta da IA não é um JSON válido") from exc
    if not isinstance(data, list):
        raise ReviewParseError("a resposta da IA não é um array JSON")
    return data


def parse_review_output(raw: str, expected_ids: list[str]) -> ParsedReview:
    """Parse the model reply against the question ids that were sent."""
    expected = set(expected_ids)
    parsed = ParsedReview()
    for entry in _extract_array(raw):
        if not isinstance(entry, dict):
            continue
        qid = entry.get("question_id")
        verdict = entry.get("verdict")
        if qid not in expected or qid in parsed.results or verdict not in ("approved", "rejected"):
            continue
        reason = str(entry.get("reason") or "").strip()[:MAX_REASON_CHARS]
        improved = entry.get("improved")
        improved = improved.strip() if isinstance(improved, str) else None
        if not improved or len(improved) > MAX_ANSWER_CHARS:
            improved = None
        parsed.results[qid] = ReviewResult(qid, verdict, reason, improved)
    parsed.missing = [q for q in expected_ids if q not in parsed.results]
    return parsed
