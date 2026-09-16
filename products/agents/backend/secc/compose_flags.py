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

import re
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

#: Contract §E.11 — one tmpfs per slot at ``/run/julia-<K>``, plus the
#: single shared ``/run/julia-handoff``. DERIVED below, never hand-copied
#: (same rationale as the module docstring for ``derive_security_flags``):
#: a compose edit that drops a slot's mount, or changes its owner/mode,
#: must change what THIS module reports too, so the SEC-C harness catches
#: it instead of silently keeping a stale hand-written expectation.
_SLOT_MOUNT_RE = re.compile(r"^/run/julia-(\d+)$")
HANDOFF_MOUNT = "/run/julia-handoff"


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


def _parse_tmpfs_entry(entry: str) -> dict[str, str]:
    """One compose ``tmpfs:`` list entry, ``"<mount>[:opt=val,...]"``, into
    ``{"mount": <mount>, "raw": <entry>, **opts}``. Pure string parsing —
    no YAML re-typing of the option values (a compose tmpfs entry is one
    YAML scalar; ``mode=0700`` stays the 4-character string ``"0700"``,
    never re-interpreted as a number)."""
    mount, _, opts_str = entry.partition(":")
    parsed: dict[str, str] = {"mount": mount, "raw": entry}
    for part in opts_str.split(","):
        part = part.strip()
        if not part:
            continue
        key, _, value = part.partition("=")
        parsed[key] = value if value else "true"
    return parsed


def slot_tmpfs_specs(compose_path: Path, service: str) -> list[dict[str, str]]:
    """Per-slot ``/run/julia-<K>`` tmpfs entries, DERIVED from the compose
    ``tmpfs:`` list (contract §E.11) — sorted by slot index, each carrying
    ``index`` (str, e.g. ``"0"``) plus every raw tmpfs option (``mount``,
    ``uid``, ``gid``, ``mode``, ``size``, ``raw``).

    Raises ``ValueError`` if the slot indices aren't a contiguous
    ``0..N-1`` run — a gap (e.g. ``julia-0`` and ``julia-2`` but no
    ``julia-1``) is a compose bug this harness must catch, never silently
    tolerate as "2 slots with weird numbering."
    """
    svc = load_service(compose_path, service)
    specs: list[dict[str, str]] = []
    for entry in svc.get("tmpfs", []):
        parsed = _parse_tmpfs_entry(entry)
        m = _SLOT_MOUNT_RE.match(parsed["mount"])
        if m:
            parsed["index"] = m.group(1)
            specs.append(parsed)
    specs.sort(key=lambda s: int(s["index"]))
    for expected, spec in enumerate(specs):
        if int(spec["index"]) != expected:
            raise ValueError(
                f"slot tmpfs mounts must be contiguous from 0; got indices "
                f"{[s['index'] for s in specs]} in {compose_path}"
            )
    return specs


def handoff_tmpfs_spec(compose_path: Path, service: str) -> dict[str, str]:
    """The single shared ``/run/julia-handoff`` tmpfs entry (contract
    §E.11). Raises ``KeyError`` (never returns ``{}``) if compose doesn't
    declare it — the harness must fail loud, not silently skip the
    handoff-mount checks."""
    svc = load_service(compose_path, service)
    for entry in svc.get("tmpfs", []):
        parsed = _parse_tmpfs_entry(entry)
        if parsed["mount"] == HANDOFF_MOUNT:
            return parsed
    raise KeyError(f"{HANDOFF_MOUNT} tmpfs mount not found in {compose_path}'s {service!r} service")


def slot_count(compose_path: Path, service: str) -> int:
    """The number of per-slot tmpfs mounts compose declares — the harness's
    OWN derived slot count, independent of (and cross-checked against) the
    image's ``JULIA_CLI_SLOTS`` env var."""
    return len(slot_tmpfs_specs(compose_path, service))


def normalize_octal_mode(raw: str) -> str:
    """``"0700"`` (compose's own literal) -> ``"700"`` (the no-leading-zero
    form the kernel reports in ``/proc/mounts`` and ``bin/entrypoint.sh``'s
    own ``_opts_has`` check compares against)."""
    return format(int(raw, 8), "o")


def normalize_size_to_kib(raw: str) -> str:
    """``"40m"`` (compose's own literal) -> ``"40960k"`` (the kernel's own
    KiB-normalized form in ``/proc/mounts`` — verified against
    ``bin/entrypoint.sh``'s own ``size=40960k`` literal). No unit suffix
    means bytes-already (defensive default; every mount this module reads
    today always carries a unit)."""
    match = re.match(r"^(\d+)([kmg]?)$", raw.strip().lower())
    if not match:
        raise ValueError(f"cannot normalize tmpfs size {raw!r}")
    value, unit = int(match.group(1)), match.group(2)
    multiplier = {"": 1, "k": 1, "m": 1024, "g": 1024 * 1024}[unit]
    return f"{value * multiplier}k"


def mutate_tmpfs_flag(flags: list[str], mount: str, new_entry: str | None) -> list[str]:
    """A NEW flag list with the ``--tmpfs=<mount>:...`` entry for ``mount``
    replaced by ``new_entry`` (a full ``"<mount>:opts"`` string), or
    removed entirely when ``new_entry`` is ``None``. Every OTHER flag
    (every other slot's mount, the handoff mount, caps, read_only, ...) is
    untouched — used by the fail-closed mount checks (missing / wrong
    owner / wrong mode) so a failure is attributable to exactly the one
    mutated mount. Raises ``ValueError`` if ``mount`` isn't found — a
    silent no-op would make the fail-closed check meaningless.
    """
    prefix = f"--tmpfs={mount}:"
    bare = f"--tmpfs={mount}"
    out: list[str] = []
    found = False
    for flag in flags:
        if flag.startswith(prefix) or flag == bare:
            found = True
            if new_entry is not None:
                out.append(f"--tmpfs={new_entry}")
            continue
        out.append(flag)
    if not found:
        raise ValueError(f"no --tmpfs flag for mount {mount!r} found in {flags!r}")
    return out
