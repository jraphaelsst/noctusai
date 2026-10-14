"""Behaviour-probe declarations for the guards (UNIQUE / CHECK / trigger) an organ's migration generator emits.

An organ declares each guard ONCE, next to its generator, as an :class:`OrganGuardProbe`: the
schema-parameterized plpgsql that tries the exact operation the guard exists to refuse. The
toolchain (`noctus.dev.verify_db_guards`) wraps each one in a rolled-back transaction and runs it
in EVERY product that rendered the organ's migration, so a render never needs a hand-written
probe or allowlist entry -- and a guard the generator adds without a probe fails the completeness
test and the `check_migration_guard_has_probe` keeper (gate and mechanism ship together).

Contract for ``body`` (plpgsql statements, schema-qualified by the factory that built it):

* it runs inside the probe's classified sub-block: setup statements that fail surface as
  ``ambiguous`` (never a false ``refused``), and the LAST statement must be the violating one;
* it must NOT raise on its own -- the harness raises the ``permitted`` finding right after it
  when nothing refused;
* it may use the variables it ``declare``s (plus ``v_org uuid``, always declared as a fresh uuid); it fabricates its own rows (a fresh ``v_org``), never borrows
  production data;
* ``fragment`` is the text that must appear in the refusal's message (a constraint/index name for
  a UNIQUE/CHECK, the RAISE text for a trigger) -- an error that does not carry it is
  ``ambiguous``, not ``refused``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

__all__ = ["OrganGuardProbe", "GuardProbeFactory"]

KINDS = ("unique", "check", "trigger")


@dataclass(frozen=True)
class OrganGuardProbe:
    #: the constraint / unique-index / trigger-function name exactly as the keeper detects it in the DDL
    guard_name: str
    kind: str  # "unique" | "check" | "trigger"
    #: unqualified table names that must exist; any missing => the probe reports ``pending`` (migration not applied yet)
    requires: tuple[str, ...]
    #: plpgsql statements, schema-qualified, ending in the violating operation (see module docstring)
    body: str
    #: what the harness reports when ``body`` unexpectedly succeeded, e.g. "a duplicate party document insert"
    permitted: str
    rationale: str
    #: text that must appear in the refusal message; defaults to ``guard_name``
    fragment: str = ""
    #: extra plpgsql DECLARE lines (e.g. ``v_a uuid;``)
    declare: str = ""
    #: tells apart two probes of ONE guard (a trigger that refuses UPDATE and DELETE separately)
    variant: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"guard {self.guard_name!r}: kind must be one of {KINDS}, got {self.kind!r}")
        if not self.requires:
            raise ValueError(f"guard {self.guard_name!r}: declare at least one required table")
        if "%" in self.permitted:
            raise ValueError(f"guard {self.guard_name!r}: `permitted` lands in a RAISE format string -- no bare %")

    @property
    def probe_key(self) -> str:
        return f"{self.guard_name}.{self.variant}" if self.variant else self.guard_name

    @property
    def refusal_fragment(self) -> str:
        return self.fragment or self.guard_name


#: `factory(schema) -> probes` -- an organ's whole guard set bound to a schema.
GuardProbeFactory = Callable[[str], Sequence[OrganGuardProbe]]
