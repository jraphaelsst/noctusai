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
    HANDOFF_MOUNT,
    derive_security_flags,
    expected_capbnd_mask,
    handoff_tmpfs_spec,
    load_service,
    mutate_tmpfs_flag,
    normalize_octal_mode,
    normalize_size_to_kib,
    slot_count,
    slot_tmpfs_specs,
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
    # contract §E.11: one tmpfs per slot, plus the shared handoff mount —
    # NOT the old single shared `/run/julia:` mount.
    assert any(f.startswith("--tmpfs=/run/julia-0:") for f in flags)
    assert any(f.startswith("--tmpfs=/run/julia-1:") for f in flags)
    assert any(f.startswith("--tmpfs=/run/julia-2:") for f in flags)
    assert any(f.startswith(f"--tmpfs={HANDOFF_MOUNT}:") for f in flags)
    assert not any(f.startswith("--tmpfs=/run/julia:") for f in flags), (
        "the old single shared /run/julia mount must be gone under §E.11"
    )
    assert any(f.startswith("--tmpfs=/tmp:") for f in flags)
    assert any(f.startswith("--shm-size=") for f in flags)
    assert any(f.startswith("--memory=") for f in flags)


def test_slot_tmpfs_specs_derives_three_contiguous_slots() -> None:
    specs = slot_tmpfs_specs(_COMPOSE_PATH, "agents")
    assert [s["index"] for s in specs] == ["0", "1", "2"]
    for k, spec in enumerate(specs):
        assert spec["mount"] == f"/run/julia-{k}"
        assert spec["uid"] == str(2000 + k)
        assert spec["gid"] == str(2000 + k)
        assert spec["mode"] == "0700"
        assert spec["size"] == "40m"
        assert spec["raw"] == (
            f"/run/julia-{k}:uid={2000 + k},gid={2000 + k},mode=0700,size=40m"
        )


def test_slot_count_matches_derived_specs() -> None:
    assert slot_count(_COMPOSE_PATH, "agents") == 3


def test_handoff_tmpfs_spec() -> None:
    spec = handoff_tmpfs_spec(_COMPOSE_PATH, "agents")
    assert spec["mount"] == HANDOFF_MOUNT
    assert spec["uid"] == "1000"
    assert spec["gid"] == "1000"
    assert spec["mode"] == "0711"


def test_handoff_tmpfs_spec_missing_raises_keyerror(tmp_path: Path) -> None:
    bogus = tmp_path / "compose.yml"
    bogus.write_text(
        "services:\n  agents:\n    tmpfs:\n      - /run/julia-0:uid=2000,gid=2000,mode=0700,size=40m\n"
    )
    with pytest.raises(KeyError, match="julia-handoff"):
        handoff_tmpfs_spec(bogus, "agents")


def test_slot_tmpfs_specs_rejects_non_contiguous_indices(tmp_path: Path) -> None:
    bogus = tmp_path / "compose.yml"
    bogus.write_text(
        "services:\n  agents:\n    tmpfs:\n"
        "      - /run/julia-0:uid=2000,gid=2000,mode=0700,size=40m\n"
        "      - /run/julia-2:uid=2002,gid=2002,mode=0700,size=40m\n"
    )
    with pytest.raises(ValueError, match="contiguous"):
        slot_tmpfs_specs(bogus, "agents")


def test_normalize_octal_mode() -> None:
    assert normalize_octal_mode("0700") == "700"
    assert normalize_octal_mode("0711") == "711"


def test_normalize_size_to_kib() -> None:
    assert normalize_size_to_kib("40m") == "40960k"
    assert normalize_size_to_kib("80m") == "81920k"
    assert normalize_size_to_kib("64m") == "65536k"


def test_mutate_tmpfs_flag_replaces_only_the_named_mount() -> None:
    flags = derive_security_flags(_COMPOSE_PATH, "agents")
    mutated = mutate_tmpfs_flag(
        flags, "/run/julia-0", "/run/julia-0:uid=9999,gid=9999,mode=0700,size=40m"
    )
    assert "--tmpfs=/run/julia-0:uid=9999,gid=9999,mode=0700,size=40m" in mutated
    assert not any(f == "--tmpfs=/run/julia-0:uid=2000,gid=2000,mode=0700,size=40m" for f in mutated)
    # every other flag survives byte-identical
    others_before = [f for f in flags if not f.startswith("--tmpfs=/run/julia-0:")]
    others_after = [f for f in mutated if not f.startswith("--tmpfs=/run/julia-0:")]
    assert others_before == others_after


def test_mutate_tmpfs_flag_can_remove_a_mount_entirely() -> None:
    flags = derive_security_flags(_COMPOSE_PATH, "agents")
    mutated = mutate_tmpfs_flag(flags, "/run/julia-1", None)
    assert not any(f.startswith("--tmpfs=/run/julia-1:") for f in mutated)
    assert len(mutated) == len(flags) - 1


def test_mutate_tmpfs_flag_unknown_mount_raises() -> None:
    flags = derive_security_flags(_COMPOSE_PATH, "agents")
    with pytest.raises(ValueError, match="no --tmpfs flag"):
        mutate_tmpfs_flag(flags, "/run/julia-99", None)


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
