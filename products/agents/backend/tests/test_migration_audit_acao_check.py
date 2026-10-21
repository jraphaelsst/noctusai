"""The audit CHECK the DB ends up with (the LAST migration that defines it) admits exactly the actions the code
writes. 034 once redefined it from a stale list and dropped 'definicao_lida' -- every Studio draft read 500'd in
prod while the 031-only pin stayed green. Pinning the latest definition closes that gap for any later file."""
from __future__ import annotations

import re
from pathlib import Path

from app.stores.studio_definitions import AUDIT_ACOES

BACKEND = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted(BACKEND.joinpath("migrations").glob("[0-9][0-9][0-9]_*.sql"))
_CHECK_RE = re.compile(r"ADD CONSTRAINT agent_audit_log_acao_check\s+CHECK \(acao IN \((.*?)\)\)", re.S)
_AUDITED_RE = re.compile(r"actor_id\(ctx\),\s*\"([a-z_]+)\"")


def _latest_check() -> tuple[str, set[str]]:
    latest = None
    for path in MIGRATIONS:
        for body in _CHECK_RE.findall(path.read_text(encoding="utf-8")):
            latest = (path.name, set(re.findall(r"'([a-z_]+)'", body)))
    assert latest is not None, "no migration defines agent_audit_log_acao_check"
    return latest


def test_latest_audit_check_matches_the_python_tuple():
    name, acoes = _latest_check()
    assert acoes == set(AUDIT_ACOES), f"{name}: missing {set(AUDIT_ACOES) - acoes}, extra {acoes - set(AUDIT_ACOES)}"


def test_every_action_a_router_audits_is_declared():
    audited = set()
    for path in BACKEND.joinpath("app").rglob("*.py"):
        audited |= set(_AUDITED_RE.findall(path.read_text(encoding="utf-8")))
    assert audited, "the audit call shape changed; update _AUDITED_RE"
    assert audited <= set(AUDIT_ACOES), f"audited but not in AUDIT_ACOES: {audited - set(AUDIT_ACOES)}"
