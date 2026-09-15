"""Derive ``docker run`` security flags from ``products/agents/docker-compose.yml``.

Pure logic, no docker/subprocess calls — unit-tested in
``tests/secc/test_compose_flags.py`` (agents backend pytest job, CI-gated).

WHY DERIVE INSTEAD OF HAND-COPY: the proof harness's whole point is that it
cannot drift from what prod actually runs. A hand-copied ``cap_drop: ALL``
literal in the harness would keep "passing" even after a real compose edit
loosened the hardening — the harness would be proving nothing. Reading the
compose file at test time means a security-block edit is caught the next
harness run, same as a doc-drift keeper.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# The one gate the compose ALSO carries that isn't a "docker run" flag in
# the classic sense: `init: true` maps 1:1 to `docker run --init`.
_MEM_LIMIT_FLAG = "--memory"
_SHM_SIZE_FLAG = "--shm-size"

#: Named security gates this module knows how to both EMIT and OMIT.
#: Keys are the gate names the fail-closed-entrypoint proof iterates over
#: (``run_proof.py``); values are the compose key(s) each gate reads.
GATE_NAMES = ("cap_drop_and_add", "no_new_privileges", "read_only")


def load_service(compose_path: Path, service: str) -> dict[str, Any]:
    """Return the ``services.<service>`` mapping from a compose file.

    Raises ``KeyError`` with the available service names if ``service``
    isn't declared — fail loud, never silently return ``{}``.
    """
    doc = yaml.safe_load(compose_path.read_text())
    services = doc.get("services", {})
    if service not in services:
        raise KeyError(
            f"service {service!r} not found in {compose_path} "
            f"(available: {sorted(services)})"
        )
    return services[service]


def derive_security_flags(
    compose_path: Path,
    service: str,
    *,
    omit_gates: frozenset[str] = frozenset(),
) -> list[str]:
    """Return the ``docker run`` flag list matching this service's compose
    hardening block exactly.

    ``omit_gates`` drops one or more of ``GATE_NAMES`` — used by the
    fail-closed-entrypoint proof to start the container WITHOUT one gate at
    a time and assert ``bin/entrypoint.sh`` refuses to boot.
    """
    for gate in omit_gates:
        if gate not in GATE_NAMES:
            raise ValueError(f"unknown gate {gate!r} (known: {GATE_NAMES})")

    svc = load_service(compose_path, service)
    flags: list[str] = []

    if "cap_drop_and_add" not in omit_gates:
        for cap in svc.get("cap_drop", []):
            flags.append(f"--cap-drop={cap}")
        for cap in svc.get("cap_add", []):
            flags.append(f"--cap-add={cap}")

    if "no_new_privileges" not in omit_gates:
        for opt in svc.get("security_opt", []):
            flags.append(f"--security-opt={opt}")

    if "read_only" not in omit_gates:
        if svc.get("read_only"):
            flags.append("--read-only")

    for mount in svc.get("tmpfs", []):
        flags.append(f"--tmpfs={mount}")

    if "shm_size" in svc:
        flags.append(f"{_SHM_SIZE_FLAG}={svc['shm_size']}")

    if "mem_limit" in svc:
        flags.append(f"{_MEM_LIMIT_FLAG}={svc['mem_limit']}")

    if svc.get("init"):
        flags.append("--init")

    return flags


def expected_capbnd_mask(compose_path: Path, service: str) -> str:
    """Recompute the CapBnd hex mask ``bin/entrypoint.sh`` hardcodes
    (``00000000000000e0``) FROM the compose ``cap_add`` list, so a compose
    edit that adds/removes a capability is caught by a mismatch here
    instead of silently leaving the entrypoint's own literal stale.

    Linux capability bit numbers (``linux/capability.h``): CAP_KILL=5,
    CAP_SETGID=6, CAP_SETUID=7. ``cap_drop: [ALL]`` means the bounding set
    is EXACTLY the ``cap_add`` list — no implicit extras.
    """
    bits = {"KILL": 5, "SETGID": 6, "SETUID": 7}
    svc = load_service(compose_path, service)
    if svc.get("cap_drop") != ["ALL"]:
        raise ValueError(
            f"expected_capbnd_mask assumes cap_drop: [ALL]; got {svc.get('cap_drop')!r}"
        )
    mask = 0
    for cap in svc.get("cap_add", []):
        try:
            mask |= 1 << bits[cap]
        except KeyError:
            raise ValueError(
                f"expected_capbnd_mask doesn't know the bit for cap {cap!r} "
                f"(known: {sorted(bits)}) — extend the table, don't hand-roll the mask."
            ) from None
    return format(mask, "016x")
