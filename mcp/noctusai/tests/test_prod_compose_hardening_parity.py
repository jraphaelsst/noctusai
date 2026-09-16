"""Colocated regression test for `check_prod_compose_hardening_parity` (meta-detector:
every keeper ships Test<CamelCase>).

roadmap julia-agents-academia-2026-09, D1 review: "the security block is generated
from one propagate source and reused by the M6 docker-compose.prod.yml entry, with
a keeper parity check."
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_prod_compose_hardening_parity  # noqa: E402
from tools.noctus.dev.propagate import (  # noqa: E402
    _C_HARDENING_ACADEMIA,
    _C_HARDENING_AGENTS,
)


def _write_prod_compose(tmp_path: Path, agents_block: str, academia_block: str) -> None:
    compose = tmp_path / "deploy" / "fleet"
    compose.mkdir(parents=True)
    text = (
        "services:\n"
        "  academia-de-reciclagem:\n"
        "    image: ghcr.io/x/noctus-academia-de-reciclagem:latest\n"
        "    expose:\n"
        '      - "8015"\n'
        f"{academia_block}"
        "  agents:\n"
        "    image: ghcr.io/x/noctus-agents:latest\n"
        "    expose:\n"
        '      - "8016"\n'
        f"{agents_block}"
        "networks:\n"
        "  noctus-net:\n"
        "    external: true\n"
    )
    (compose / "docker-compose.prod.yml").write_text(text, encoding="utf-8")


class TestProdComposeHardeningParity:
    def test_no_prod_compose_file_is_clean(self, tmp_path):
        # Not a noc tree yet / fleet compose absent — silent skip, not an error.
        assert check_prod_compose_hardening_parity(repo_root=tmp_path) == []

    def test_exact_reuse_of_propagate_source_is_clean(self, tmp_path):
        _write_prod_compose(tmp_path, _C_HARDENING_AGENTS, _C_HARDENING_ACADEMIA)
        assert check_prod_compose_hardening_parity(repo_root=tmp_path) == []

    def test_hand_retyped_agents_block_flags_drift(self, tmp_path):
        # One character off (a dropped cap) from the canonical constant —
        # exactly the drift class this keeper exists to catch.
        drifted_agents = _C_HARDENING_AGENTS.replace("      - KILL\n", "")
        _write_prod_compose(tmp_path, drifted_agents, _C_HARDENING_ACADEMIA)
        issues = check_prod_compose_hardening_parity(repo_root=tmp_path)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "prod-compose-hardening-drift"
        assert "agents" in issues[0]["issue"]
        assert issues[0]["severity"] == "high"

    def test_missing_academia_block_flags_drift(self, tmp_path):
        _write_prod_compose(tmp_path, _C_HARDENING_AGENTS, "")
        issues = check_prod_compose_hardening_parity(repo_root=tmp_path)
        assert len(issues) == 1
        assert "academia-de-reciclagem" in issues[0]["issue"]

    def test_both_missing_flags_two_issues(self, tmp_path):
        _write_prod_compose(tmp_path, "", "")
        issues = check_prod_compose_hardening_parity(repo_root=tmp_path)
        assert len(issues) == 2
        slugs = {i["issue"].split("'")[1] for i in issues}
        assert slugs == {"agents", "academia-de-reciclagem"}
