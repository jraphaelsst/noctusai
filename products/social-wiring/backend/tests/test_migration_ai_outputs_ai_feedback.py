"""social_wiring.ai_outputs / ai_feedback, pasted from the seed templates.

Pins parity (the migration body IS sql_templates' output, so a template fix is
never silently missing here) and that email_marketing no longer targets the
retired `mailing` schema (owner, 2026-10-10)."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.domain.sql_templates import ai_feedback_table_sql, ai_outputs_table_sql
from noctusai_lib.testing.migrations import migration_path

_BACKEND = Path(__file__).resolve().parents[1]
_MIGRATION = migration_path(_BACKEND / "migrations", "ai_outputs_ai_feedback")


def test_migration_is_the_seed_templates_verbatim():
    sql = _MIGRATION.read_text(encoding="utf-8")
    assert ai_outputs_table_sql("social_wiring") in sql
    assert ai_feedback_table_sql("social_wiring") in sql


def test_email_marketing_never_targets_the_retired_mailing_schema():
    offenders = []
    for path in (_BACKEND / "app" / "modules" / "email_marketing").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"""schema\s*=\s*["']mailing["']|["']mailing\.[a-z_]+["']|product\s*=\s*["']mailing["']""", text):
            offenders.append(str(path.relative_to(_BACKEND)))
    assert offenders == []
