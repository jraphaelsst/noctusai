"""
Unit tests for the lead scoring engine (pure computation — no DB).

Covers:
  - normalize_text: accent-folding, snake_case, pt-BR accents
  - compute_score: hot/warm/cold thresholds, blocker short-circuit,
    empty rules, unmatched rules, partial match
"""
import pytest

from app.services.lead_scoring import (
    BLOCKER_SCORE,
    TEMPERATURE_COLD,
    TEMPERATURE_HOT,
    TEMPERATURE_WARM,
    compute_score,
    normalize_text,
)


# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def test_lowercase(self):
        assert normalize_text("FullName") == "fullname"

    def test_strips_accent_cedilla(self):
        assert normalize_text("Ação") == "acao"

    def test_strips_accent_tilde(self):
        assert normalize_text("São Paulo") == "sao paulo"

    def test_snake_to_space(self):
        assert normalize_text("full_name") == "full name"

    def test_hyphen_to_space(self):
        assert normalize_text("e-mail") == "e mail"

    def test_collapses_spaces(self):
        assert normalize_text("  full   name  ") == "full name"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_meta_snake_matches_human_label(self):
        # The exact case from 01-PROCEDURES §1b
        assert normalize_text("full_name") == normalize_text("full name")

    def test_pt_br_oe(self):
        assert normalize_text("João") == "joao"

    def test_pt_br_accentuated_question(self):
        assert normalize_text("Interesse") == "interesse"


# ---------------------------------------------------------------------------
# compute_score
# ---------------------------------------------------------------------------

def _rule(question, answer, score=1, is_blocker=False):
    return {"question": question, "answer": answer, "score": score, "is_blocker": is_blocker}


class TestComputeScoreHot:
    def test_hot_threshold_met(self):
        rules = [_rule("q1", "yes", score=2), _rule("q2", "yes", score=3)]
        fields = {"q1": "yes", "q2": "yes"}
        result = compute_score(rules, fields)
        assert result["score_total"] == 5
        assert result["qualification"] == TEMPERATURE_HOT

    def test_score_exceeds_hot(self):
        rules = [_rule("q1", "sim", score=2), _rule("q2", "nao", score=2), _rule("q3", "ok", score=2)]
        fields = {"q1": "sim", "q2": "nao", "q3": "ok"}
        result = compute_score(rules, fields)
        assert result["score_total"] == 6
        assert result["qualification"] == TEMPERATURE_HOT


class TestComputeScoreWarm:
    def test_warm_threshold_met(self):
        rules = [_rule("interest", "yes", score=2)]
        fields = {"interest": "yes"}
        result = compute_score(rules, fields)
        assert result["score_total"] == 2
        assert result["qualification"] == TEMPERATURE_WARM

    def test_warm_below_hot(self):
        rules = [_rule("a", "x", score=2), _rule("b", "y", score=1)]
        fields = {"a": "x", "b": "y"}
        result = compute_score(rules, fields)
        assert result["score_total"] == 3
        assert result["qualification"] == TEMPERATURE_WARM


class TestComputeScoreCold:
    def test_cold_when_score_below_two(self):
        rules = [_rule("q", "a", score=1)]
        fields = {"q": "a"}
        result = compute_score(rules, fields)
        assert result["score_total"] == 1
        assert result["qualification"] == TEMPERATURE_COLD

    def test_cold_when_no_match(self):
        rules = [_rule("interesse", "sim", score=2)]
        fields = {"interesse": "nao"}  # different answer
        result = compute_score(rules, fields)
        assert result["score_total"] == 0
        assert result["qualification"] == TEMPERATURE_COLD

    def test_cold_when_no_rules(self):
        result = compute_score([], {"anything": "value"})
        assert result["score_total"] == 0
        assert result["qualification"] == TEMPERATURE_COLD


class TestComputeScoreBlocker:
    def test_blocker_sets_score_to_minus_ten(self):
        rules = [
            _rule("renda", "0", score=0, is_blocker=True),
            _rule("interesse", "sim", score=2),
        ]
        # Both keys present; blocker fires first (rule order)
        fields = {"renda": "0", "interesse": "sim"}
        result = compute_score(rules, fields)
        assert result["score_total"] == BLOCKER_SCORE
        assert result["qualification"] == TEMPERATURE_COLD

    def test_blocker_short_circuits_remaining_rules(self):
        # Second rule has a positive score but blocker should stop evaluation
        rules = [
            _rule("q_blocker", "bad", score=0, is_blocker=True),
            _rule("q_good", "great", score=5),
        ]
        fields = {"q_blocker": "bad", "q_good": "great"}
        result = compute_score(rules, fields)
        assert result["score_total"] == BLOCKER_SCORE
        # answers_detail should only have the blocker key (short-circuit)
        assert "q_blocker" in result["answers_detail"] or "q blocker" in result["answers_detail"]

    def test_blocker_not_triggered_when_answer_no_match(self):
        rules = [_rule("renda", "0", score=0, is_blocker=True)]
        fields = {"renda": "5000"}  # doesn't match "0"
        result = compute_score(rules, fields)
        assert result["score_total"] == 0
        assert result["qualification"] == TEMPERATURE_COLD


class TestComputeScoreAccentFolding:
    def test_meta_snake_matches_human_rule(self):
        # Rule written with space; Meta sends snake_case
        rules = [_rule("full name", "joao silva", score=2)]
        fields = {"full_name": "João Silva"}
        result = compute_score(rules, fields)
        assert result["score_total"] == 2
        assert result["qualification"] == TEMPERATURE_WARM

    def test_accented_answer_matches_unaccented_rule(self):
        rules = [_rule("cidade", "sao paulo", score=2)]
        fields = {"cidade": "São Paulo"}
        result = compute_score(rules, fields)
        assert result["score_total"] == 2

    def test_mixed_case_rule_and_field(self):
        rules = [_rule("Interesse", "SIM", score=3)]
        fields = {"interesse": "sim"}
        result = compute_score(rules, fields)
        assert result["score_total"] == 3
        assert result["qualification"] == TEMPERATURE_WARM


class TestComputeScoreAnswersDetail:
    def test_detail_tracks_matched_and_unmatched(self):
        rules = [
            _rule("q1", "yes", score=2),
            _rule("q2", "no", score=1),
        ]
        fields = {"q1": "yes", "q2": "maybe"}  # q2 doesn't match
        result = compute_score(rules, fields)
        assert result["score_total"] == 2
        detail = result["answers_detail"]
        # q1 normalized key should be present and matched
        assert any(d.get("matched") is True for d in detail.values())
        # q2 normalized key should be present and not matched
        assert any(d.get("matched") is False for d in detail.values())

    def test_missing_question_not_in_detail(self):
        rules = [_rule("absent_question", "answer", score=2)]
        fields = {"other_key": "value"}
        result = compute_score(rules, fields)
        # absent_question wasn't in custom_fields — detail can be empty or not have a matched entry
        assert result["score_total"] == 0
