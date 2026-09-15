"""Unit tests for ``secc.compose_flags`` — the pure compose→docker-run-flags
derivation the SEC-C real-image proof harness depends on (roadmap
``julia-agents-academia-2026-09``, row SEC-C). Runs against the REAL
``products/agents/docker-compose.yml`` on disk, not a fixture copy — so a
compose edit that drops a gate is caught here too, not only by the
(non-CI) real-image proof.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from secc.compose_flags import (
    GATE_NAMES,
    derive_security_flags,
    expected_capbnd_mask,
    load_service,
)

_COMPOSE_PATH = Path(__file__).resolve().parents[3] / "docker-compose.yml"


def test_compose_file_exists() -> None:
    assert _COMPOSE_PATH.is_file(), _COMPOSE_PATH


def test_load_service_returns_agents_mapping() -> None:
    svc = load_service(_COMPOSE_PATH, "agents")
    assert svc["cap_drop"] == ["ALL"]
    assert svc["read_only"] is True


def test_load_service_unknown_service_raises_with_available_names() -> None:
    with pytest.raises(KeyError, match="agents"):
        load_service(_COMPOSE_PATH, "does-not-exist")


def test_derive_security_flags_full_hardening() -> None:
    flags = derive_security_flags(_COMPOSE_PATH, "agents")
    assert "--cap-drop=ALL" in flags
    assert "--cap-add=SETUID" in flags
    assert "--cap-add=SETGID" in flags
    assert "--cap-add=KILL" in flags
    assert "--security-opt=no-new-privileges:true" in flags
    assert "--read-only" in flags
    assert "--init" in flags
    assert any(f.startswith("--tmpfs=/run/julia:") for f in flags)
    assert any(f.startswith("--tmpfs=/tmp:") for f in flags)
    assert any(f.startswith("--shm-size=") for f in flags)
    assert any(f.startswith("--memory=") for f in flags)


@pytest.mark.parametrize("gate", GATE_NAMES)
def test_omit_gate_drops_only_that_gate(gate: str) -> None:
    full = derive_security_flags(_COMPOSE_PATH, "agents")
    without = derive_security_flags(
        _COMPOSE_PATH, "agents", omit_gates=frozenset({gate})
    )
    assert len(without) < len(full), f"omitting {gate!r} changed nothing"

    if gate == "cap_drop_and_add":
        assert not any(f.startswith("--cap-drop=") for f in without)
        assert not any(f.startswith("--cap-add=") for f in without)
    elif gate == "no_new_privileges":
        assert not any(f.startswith("--security-opt=") for f in without)
    elif gate == "read_only":
        assert "--read-only" not in without

    # every OTHER gate's flags must survive untouched
    other_full = [f for f in full if f not in without]
    for f in other_full:
        if gate == "cap_drop_and_add":
            assert f.startswith("--cap-drop=") or f.startswith("--cap-add=")
        elif gate == "no_new_privileges":
            assert f.startswith("--security-opt=")
        elif gate == "read_only":
            assert f == "--read-only"


def test_derive_security_flags_rejects_unknown_gate() -> None:
    with pytest.raises(ValueError, match="unknown gate"):
        derive_security_flags(_COMPOSE_PATH, "agents", omit_gates=frozenset({"bogus"}))


def test_expected_capbnd_mask_matches_entrypoint_literal() -> None:
    # bin/entrypoint.sh hardcodes EXPECTED_BND="00000000000000e0" for
    # SETUID+SETGID+KILL — this recomputes that mask FROM the compose
    # cap_add list so the two can never silently diverge.
    assert expected_capbnd_mask(_COMPOSE_PATH, "agents") == "00000000000000e0"


def test_expected_capbnd_mask_rejects_non_all_cap_drop(tmp_path: Path) -> None:
    bogus = tmp_path / "compose.yml"
    bogus.write_text(
        "services:\n  agents:\n    cap_drop: [NET_RAW]\n    cap_add: [KILL]\n"
    )
    with pytest.raises(ValueError, match="cap_drop"):
        expected_capbnd_mask(bogus, "agents")


def test_expected_capbnd_mask_rejects_unknown_cap(tmp_path: Path) -> None:
    bogus = tmp_path / "compose.yml"
    bogus.write_text(
        "services:\n  agents:\n    cap_drop: [ALL]\n    cap_add: [NET_ADMIN]\n"
    )
    with pytest.raises(ValueError, match="NET_ADMIN"):
        expected_capbnd_mask(bogus, "agents")
