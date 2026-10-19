"""The pre-rename `LAIS_*` env spellings still drive the renamed settings (deploy `.env` continuity).
NOC-REMEDIATE[drop-lais-env-alias]: delete with the alias in app/config.py."""
from __future__ import annotations

from app.config import SocialWiringSettings


def test_the_new_and_the_legacy_env_names_both_set_the_field(monkeypatch):
    monkeypatch.setenv("LAIS_REENGAJAMENTO_WORKER_ENABLED", "false")
    monkeypatch.setenv("JULIA_AGENTE_MAX_CONCURRENT_TURNS", "7")
    s = SocialWiringSettings()
    assert s.julia_reengajamento_worker_enabled is False and s.julia_agente_max_concurrent_turns == 7


def test_defaults_and_init_by_field_name_are_unchanged():
    s = SocialWiringSettings(julia_agente_batch_max_chars=5)
    assert s.julia_agente_batch_max_chars == 5 and s.julia_reengajamento_worker_enabled is True
