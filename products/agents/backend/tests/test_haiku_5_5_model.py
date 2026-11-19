"""claude-haiku-5-5 is selectable everywhere a model is chosen: draft settings,
persona, eval-run draft model, the seed price registry, and migration 091 (the
three DB CHECKs). No agent's model is changed by this slice."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.integrations.llm.models import MODELS as REGISTRY, is_priced
from noctusai_lib.testing.migrations import migration_sql

from app.stores.personas import MODELS as PERSONA_MODELS
from app.stores.studio_definitions import ANTHROPIC_MODELS, MODELS_BY_PROVIDER
from app.studio.models import ANTHROPIC_MODELS as SOURCE, EVAL_RUN_MODEL_ALLOWLIST

NEW = "claude-haiku-5-5"
SQL = migration_sql(Path(__file__).resolve().parents[1], "haiku_5_5_model")


def _in(fragment: str) -> set[str]:
    return set(re.findall(r"'([^']+)'", fragment))


def test_backend_lists_derive_from_one_source():
    assert NEW in SOURCE
    assert ANTHROPIC_MODELS is SOURCE and PERSONA_MODELS is SOURCE
    assert MODELS_BY_PROVIDER["anthropic"] is SOURCE
    assert NEW in EVAL_RUN_MODEL_ALLOWLIST


def test_seed_registry_prices_it_for_anthropic():
    entry = next(m for m in REGISTRY if m.id == NEW)
    assert entry.provider == "anthropic" and entry.kind == "chat" and is_priced(entry)


def test_migration_checks_match_python_lists():
    pers = SQL[SQL.index("ADD CONSTRAINT agent_personas_model_check"):]
    assert _in(pers[: pers.index(";")]) == set(SOURCE)
    ver = SQL[SQL.index("ADD CONSTRAINT agent_versions_model_check"):]
    ver = ver[: ver.index(");")]
    for provider, models in MODELS_BY_PROVIDER.items():
        m = re.search(rf"provider = '{provider}'\s+AND model IN \(([^)]*)\)", ver)
        assert m and _in(m.group(1)) == set(models), provider
    ev = SQL[SQL.index("ADD CONSTRAINT eval_runs_modelo_geracao_check"):]
    assert _in(ev[: ev.index(";")]) == set(EVAL_RUN_MODEL_ALLOWLIST)
