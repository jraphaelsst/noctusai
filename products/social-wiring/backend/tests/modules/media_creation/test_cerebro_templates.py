"""Segundo Cérebro — static templates / questions / prompts (no HTTP)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.modules.media_creation.cerebro_templates import (
    TEMPLATES,
    TEMPLATES_BY_SLUG,
    question_group,
    question_id,
    seed_sql,
)
from app.modules.media_creation.prompts.cerebro_review import (
    ReviewItem,
    ReviewParseError,
    build_review_user_message,
    parse_review_output,
)
from app.modules.media_creation.prompts.cerebro_synthesis import (
    ELEMENTOS_HEADING,
    OUTLINES,
    build_synthesis_system_prompt,
    build_synthesis_user_message,
)
from app.modules.media_creation.prompts.methodology import METODO_STRUCTURE

_MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
_FILES = sorted(_MIGRATIONS.glob("*_cs_cerebro.sql"))


class TestTemplates:
    def test_four_templates_with_the_contract_counts(self):
        assert [t.slug for t in sorted(TEMPLATES, key=lambda t: t.sort_order)] == [
            "historia-de-criacao", "historias-de-vida", "metodo-do-especialista", "nucleo-de-influencia",
        ]
        assert {t.slug: len(t.questions) for t in TEMPLATES} == {
            "nucleo-de-influencia": 15, "historia-de-criacao": 9,
            "historias-de-vida": 4, "metodo-do-especialista": 7,
        }
        assert [t.name for t in TEMPLATES] == [
            "História de Criação", "Histórias de Vida do Especialista",
            "Método do Especialista", "Núcleo de Influência",
        ]

    def test_hints_exist_only_for_nucleo_and_optional_set_is_the_draft_one(self):
        nucleo = TEMPLATES_BY_SLUG["nucleo-de-influencia"]
        assert all(q.hint for q in nucleo.questions)
        assert [q.position for q in nucleo.questions if q.optional] == [2, 4, 7, 13, 15]
        for slug in ("historia-de-criacao", "historias-de-vida", "metodo-do-especialista"):
            assert all(q.hint is None and not q.optional for q in TEMPLATES_BY_SLUG[slug].questions)

    def test_verbatim_anchor_questions(self):
        assert TEMPLATES_BY_SLUG["nucleo-de-influencia"].questions[0].text == "Qual é o seu nome, e o que você faz?"
        assert TEMPLATES_BY_SLUG["metodo-do-especialista"].questions[6].text.endswith("Qual é?")

    def test_ids_and_groups_of_three(self):
        assert question_id("nucleo-de-influencia", 3) == "nucleo-de-influencia.03"
        assert [question_group(p) for p in range(1, 8)] == [0, 0, 0, 1, 1, 1, 2]

    def test_migration_carries_the_generated_seed_verbatim(self):
        assert len(_FILES) == 1, _FILES
        sql = _FILES[0].read_text()
        assert seed_sql() in sql
        assert "social-wiring-cerebro" in sql and "'media-creation-cerebro', 'desenvolvimento'" in sql
        assert "cs_brain_append" in sql and "NOC-REMEDIATE[fk-transcricoes]" in sql
        # transcricao_id stays a plain uuid until social_wiring.transcricoes exists
        assert not re.search(r"transcricao_id\s+UUID\s+REFERENCES", sql)
        assert "cs_transcriptions" not in sql


class TestReviewParser:
    IDS = ["a.01", "a.02", "a.03"]

    def test_valid_array_with_fences_and_extras(self):
        raw = "```json\n" + json.dumps([
            {"question_id": "a.01", "verdict": "approved", "reason": "ok", "improved": None},
            {"question_id": "a.02", "verdict": "rejected", "reason": "vago", "improved": "melhor"},
            {"question_id": "zzz", "verdict": "approved", "reason": "x", "improved": None},
            {"question_id": "a.03", "verdict": "talvez", "reason": "x", "improved": None},
        ]) + "\n```"
        res = parse_review_output(raw, self.IDS)
        assert set(res.results) == {"a.01", "a.02"}          # unknown id + bad verdict ignored
        assert res.results["a.02"].improved == "melhor"
        assert res.missing == ["a.03"]

    def test_prose_around_the_array_is_tolerated(self):
        raw = 'Aqui está: [{"question_id":"a.01","verdict":"approved","reason":"ok","improved":null}] fim'
        assert parse_review_output(raw, ["a.01"]).results["a.01"].verdict == "approved"

    @pytest.mark.parametrize("raw", ["", "não sei", "{}", '{"question_id": "a.01"}', "[{"])
    def test_non_array_raises(self, raw):
        with pytest.raises(ReviewParseError):
            parse_review_output(raw, self.IDS)

    def test_oversized_improved_is_dropped_not_truncated(self):
        raw = json.dumps([{"question_id": "a.01", "verdict": "rejected", "reason": "r", "improved": "x" * 10_001}])
        assert parse_review_output(raw, ["a.01"]).results["a.01"].improved is None

    def test_user_message_carries_question_hint_and_answer(self):
        msg = build_review_user_message("Núcleo", [ReviewItem("a.01", "Pergunta?", "dica", True, "resposta")])
        assert "Pergunta?" in msg and "dica" in msg and "resposta" in msg and "Núcleo" in msg


class TestSynthesisPrompt:
    def test_every_template_has_an_outline_and_the_closing_section(self):
        assert set(OUTLINES) == set(TEMPLATES_BY_SLUG)
        for slug, headings in OUTLINES.items():
            prompt = build_synthesis_system_prompt(slug)
            assert all(f"### {h}" in prompt for h in headings)
            assert ELEMENTOS_HEADING in prompt

    def test_nucleo_outline_is_the_owners_live_one(self):
        assert OUTLINES["nucleo-de-influencia"] == (
            "Perfil Profissional", "Público-Alvo e Desafios", "Solução e Transformação", "Histórias de Sucesso",
        )

    def test_prompt_pins_the_method_audience_rules(self):
        prompt = build_synthesis_system_prompt("nucleo-de-influencia")
        assert "PRESERVE LITERALMENTE" in prompt and "NUNCA invente" in prompt and "PRIMEIRA PESSOA" in prompt
        # the coined names feed the beats these roles name in Método Audience
        for beat in ("identificacao", "virada", "nome"):
            assert f"**{beat}**" in METODO_STRUCTURE

    def test_user_message_numbers_pairs_with_hints(self):
        msg = build_synthesis_user_message("Núcleo", [("P1?", "dica", "R1"), ("P2?", None, "R2")])
        assert "1. P1?" in msg and "(dica: dica)" in msg and "Resposta: R2" in msg
