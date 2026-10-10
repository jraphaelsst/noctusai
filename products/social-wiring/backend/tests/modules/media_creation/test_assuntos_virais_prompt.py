"""Assuntos Virais — extractor prompt + output parser."""
from __future__ import annotations

from app.modules.media_creation.prompts.assuntos_virais_extractor import (
    ASSUNTOS_VIRAIS_SYSTEM_PROMPT,
    MAX_TOPICS_PER_POST,
    TOPIC_MAX_CHARS,
    parse_assuntos_output,
)


def test_prompt_is_draft_and_states_the_limits():
    import app.modules.media_creation.prompts.assuntos_virais_extractor as m

    assert "DRAFT — awaiting owner validation" in m.__doc__
    assert str(MAX_TOPICS_PER_POST) in ASSUNTOS_VIRAIS_SYSTEM_PROMPT
    assert str(TOPIC_MAX_CHARS) in ASSUNTOS_VIRAIS_SYSTEM_PROMPT


def test_clean_lines_pass_markers_and_hints_stripped():
    reply = "emagrecimento após os 40\n- sono e ansiedade (dor)\n2. Dieta low carb\n"
    topics, desc = parse_assuntos_output(reply)
    assert topics == ["emagrecimento após os 40", "sono e ansiedade", "Dieta low carb"]
    assert desc == 0


def test_chatter_and_length_rules_are_discarded_and_counted():
    reply = (
        "Aqui estão os assuntos:\n"          # ends with ':'
        "x\n"                                 # too short
        + "a" * (TOPIC_MAX_CHARS + 1) + "\n"  # too long
        "Esse post fala sobre vários temas diferentes de saúde\n"  # sentence-shaped (words)
        "dieta low carb\n"
    )
    topics, desc = parse_assuntos_output(reply)
    assert topics == ["dieta low carb"] and desc == 4


def test_dedupe_within_post_and_cap():
    reply = "Dieta\ndieta\n" + "\n".join(f"assunto {i}" for i in range(MAX_TOPICS_PER_POST + 2))
    topics, desc = parse_assuntos_output(reply)
    assert len(topics) == MAX_TOPICS_PER_POST and topics[0] == "Dieta"
    assert desc == 3  # the case-insensitive duplicate is not an error; 3 over the cap are


def test_empty_reply():
    assert parse_assuntos_output("") == ([], 0)
    assert parse_assuntos_output("\n  \n") == ([], 0)
