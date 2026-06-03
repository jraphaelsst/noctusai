"""
Lead scoring engine — accent-folded pt-BR normalizer + score computation.

Absorbs the "crown jewel" from Orbity's 01-PROCEDURES §1b with the
'ABSORB-AS-IS' verdict from 13-SALVAGE #9:

    "Matching is accent-folded + underscore/space-normalized on BOTH the
     question and the answer (NFD strip) — this handles Meta's full_name
     snake_case vs a human rule labeled 'full name', and pt-BR accents."

Temperature thresholds (from §1b):
  score >= 5 → hot
  score >= 2 → warm
  else        → cold
  any blocker → score = -10, temperature = cold (short-circuits)

No silent errors: non-matching questions are skipped (not zeroed silently
without logging). Unknown form_id returns an empty result with score=0.
"""
from __future__ import annotations

import logging
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Normalizer (ABSORB-AS-IS from 13-SALVAGE #9)
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Accent-fold + underscore/space-normalize for pt-BR form-field matching.

    Handles:
      - Meta snake_case keys  (full_name → full name → fullname)
      - pt-BR accents         (Ação → acao)
      - mixed case            (João → joao)

    Steps:
      1. Lowercase
      2. NFD decompose → strip combining chars (strip accents)
      3. Replace underscore and hyphen with space
      4. Collapse multiple spaces → single space
      5. Strip leading/trailing whitespace
    """
    if not text:
        return ""
    lowered = text.lower()
    # NFD decompose then filter out combining codepoints (accents)
    decomposed = unicodedata.normalize("NFD", lowered)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    # Normalize separators
    spaced = stripped.replace("_", " ").replace("-", " ")
    return " ".join(spaced.split())


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------

TEMPERATURE_HOT  = "hot"
TEMPERATURE_WARM = "warm"
TEMPERATURE_COLD = "cold"

HOT_THRESHOLD  = 5
WARM_THRESHOLD = 2
BLOCKER_SCORE  = -10


def _classify_temperature(score: int) -> str:
    if score >= HOT_THRESHOLD:
        return TEMPERATURE_HOT
    if score >= WARM_THRESHOLD:
        return TEMPERATURE_WARM
    return TEMPERATURE_COLD


def compute_score(
    rules: list[dict[str, Any]],
    custom_fields: dict[str, Any],
) -> dict[str, Any]:
    """Run lead_scoring_rules against a lead's custom_fields.

    Args:
        rules: rows from orbity.lead_scoring_rules for this form_id.
               Each row: {question, answer, score, is_blocker}.
        custom_fields: the lead's JSONB custom_fields dict (raw form answers).

    Returns:
        {
          "score_total": int,
          "qualification": "hot"|"warm"|"cold",
          "answers_detail": {question_key: {"matched": bool, "score": int}},
        }

    No silent errors: unmatched rules are logged at DEBUG (not suppressed).
    """
    if not rules:
        logger.debug("compute_score: no rules provided, score=0")
        return {
            "score_total": 0,
            "qualification": TEMPERATURE_COLD,
            "answers_detail": {},
        }

    # Build a normalized lookup from the lead's custom_fields
    # key: normalize_text(field_key) → (original_value, normalized_value)
    normalized_fields: dict[str, tuple[str, str]] = {}
    for field_key, field_val in custom_fields.items():
        norm_key = normalize_text(str(field_key))
        norm_val = normalize_text(str(field_val)) if field_val is not None else ""
        normalized_fields[norm_key] = (str(field_val), norm_val)

    score_total = 0
    answers_detail: dict[str, dict[str, Any]] = {}
    blocker_hit = False

    for rule in rules:
        norm_question = normalize_text(rule["question"])
        norm_answer   = normalize_text(rule["answer"])
        rule_score    = int(rule["score"])
        is_blocker    = bool(rule["is_blocker"])

        if norm_question not in normalized_fields:
            logger.debug(
                "compute_score: question %r not in custom_fields (normalized: %r)",
                rule["question"],
                norm_question,
            )
            continue

        _raw_val, lead_norm_val = normalized_fields[norm_question]
        matched = lead_norm_val == norm_answer

        if matched:
            if is_blocker:
                logger.warning(
                    "compute_score: blocker rule matched — question=%r answer=%r",
                    rule["question"],
                    rule["answer"],
                )
                blocker_hit = True
                # Short-circuit: no need to keep scoring
                answers_detail[norm_question] = {"matched": True, "score": BLOCKER_SCORE, "blocker": True}
                break

            score_total += rule_score
            answers_detail[norm_question] = {"matched": True, "score": rule_score}
        else:
            logger.debug(
                "compute_score: rule not matched question=%r expected=%r got=%r",
                rule["question"],
                rule["answer"],
                _raw_val,
            )
            answers_detail[norm_question] = {"matched": False, "score": 0}

    if blocker_hit:
        score_total = BLOCKER_SCORE

    qualification = _classify_temperature(score_total)

    return {
        "score_total": score_total,
        "qualification": qualification,
        "answers_detail": answers_detail,
    }
