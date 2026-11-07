"""Rendering + config rules of the transition-log primitive (pure, no database)."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.sql_templates import GUC_GUARD_MARKER
from noctusai_lib.domain.transition_log import (
    CONFIG_MARKER,
    MIGRATION_HEADER,
    KeyColumn,
    TransitionLogConfig,
    configs_in_migration,
    normalize_key,
    normalize_subject,
    transition_log_backfill_sql,
    transition_log_guard_probes,
    transition_log_migration,
)

from .conformance import CARD, PARTICIPANT


def test_render_starts_with_the_header_and_carries_its_config():
    sql = transition_log_migration(CARD) + transition_log_migration(PARTICIPANT, header=False)
    assert sql.startswith(MIGRATION_HEADER + "\n")
    assert sql.count(MIGRATION_HEADER) == 1 and sql.count(CONFIG_MARKER) == 2
    assert configs_in_migration(sql) == [CARD, PARTICIPANT]  # the marker round-trips the full config
    assert GUC_GUARD_MARKER in sql  # immutability comes from the seed guard, never a hand-written copy


def test_render_never_cascades_and_keys_the_composite_entity():
    sql = transition_log_migration(PARTICIPANT)
    assert "CASCADE" not in sql.upper()
    assert "uq_participant_events_entity_seq ON tlc.participant_events (thread_id, agent_id, seq)" in sql
    assert "idx_participant_events_org_entity_seq ON tlc.participant_events (org_id, thread_id, agent_id, seq)" in sql
    assert "REFERENCES tlc.participants (thread_id, agent_id) ON DELETE NO ACTION" in sql


def test_render_is_deterministic():
    assert transition_log_migration(CARD) == transition_log_migration(CARD)


def test_backfill_statement():
    assert transition_log_backfill_sql(CARD) == "SELECT tlc.card_backfill_initial_state(NULL);"
    assert "'00000000-0000-0000-0000-0000000000a1'::uuid" in transition_log_backfill_sql(CARD, "00000000-0000-0000-0000-0000000000a1")


@pytest.mark.parametrize("kwargs", [
    {"aggregate": "Bad-Name"},
    {"state_type": "jsonb"},
    {"key": ()},
    {"key": (KeyColumn("seq"),)},
    {"key": (KeyColumn("a"), KeyColumn("a"))},
    {"actor_kinds": ("user", "synthetic")},
    {"aggregate": "x" * 40},
])
def test_invalid_configs_are_refused(kwargs):
    base = dict(schema="s", aggregate="agg", state_table="t", state_column="c")
    with pytest.raises(ValueError):
        TransitionLogConfig(**{**base, **kwargs})


def test_key_normalisation():
    assert normalize_key(CARD, "abc") == {"entity_id": "abc"}
    assert normalize_key(PARTICIPANT, {"thread_id": "t", "agent_id": "a"}) == {"thread_id": "t", "agent_id": "a"}
    with pytest.raises(ValueError):
        normalize_key(PARTICIPANT, "t")  # composite needs a mapping
    with pytest.raises(ValueError):
        normalize_key(PARTICIPANT, {"thread_id": "t"})
    assert normalize_subject(PARTICIPANT, {"thread_id": "t"}) == {"thread_id": "t"}
    with pytest.raises(ValueError):
        normalize_subject(PARTICIPANT, {"agent": "x"})


def test_every_rendered_guard_has_a_probe():
    names = {p.guard_name for p in transition_log_guard_probes(PARTICIPANT)}
    assert names == {
        "guard_participant_events_append_only", "participant_events_refuse_truncate",
        "transition_log_erasures_append_only", "transition_log_erasures_reason_present",
        "uq_participant_events_entity_seq", "participant_events_seq_positive", "participant_events_creation_first",
        "participant_events_event_type_shape", "participant_events_data_object", "participant_events_actor_kind",
    }
