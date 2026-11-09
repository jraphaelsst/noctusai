"""Value objects + the ``OutputGuard`` Protocol of the LLM guardrails organ.

Policy is DATA: a product passes :class:`GuardContext` (the facts of one reply) and per-rule parameters; nothing in the organ
names a tenant, a persona or a prompt. A finding carries rule + policy + CODES/COUNTS only.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = ["GENERIC_RULES", "GuardContext", "GuardFinding", "GuardRule", "OutputGuard"]

#: The product-neutral output rules, in evaluation order.
GENERIC_RULES: tuple[str, ...] = (
    "vazamento_prompt", "link_nao_permitido", "contato_nao_permitido", "pii_na_resposta", "formato_suspeito",
    "padroes_proibidos",
)


@dataclass(frozen=True)
class GuardContext:
    """The facts of one reply the generic detectors read (all data the product supplies)."""

    lead_messages: Sequence[str] = ()
    allowed_links: Iterable[str] = ()
    allowed_domains: Iterable[str] = ()
    allowed_contacts: Iterable[str] = ()
    own_company_ids: Iterable[str] = ()
    #: per-org/version canary appended to the system prompt; its appearance in a reply is a leak
    canary: str | None = None
    #: stored prompt fingerprint (``.shingle_tokens`` + ``.shingles``)
    fingerprint: Any | None = None
    #: fingerprint of prompt-derived text handed to the model this turn (a longer window)
    derived_fingerprint: Any | None = None
    #: org data values whose quotation is not a leak
    org_data: Iterable[str] = ()


@dataclass(frozen=True)
class GuardRule:
    """One rule's configuration: its policy (``bloquear`` | ``registrar`` | ...) and parameters (DATA)."""

    policy: str = "registrar"
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GuardFinding:
    rule: str
    policy: str
    detail: dict[str, Any]


@runtime_checkable
class OutputGuard(Protocol):
    def evaluate(
        self, rule: str, reply: str, ctx: GuardContext, params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """One generic rule over ``reply``; ``None`` = clean. Counts/codes only."""
        ...

    def check(self, reply: str, ctx: GuardContext, rules: Mapping[str, GuardRule]) -> list[GuardFinding]:
        """Every generic rule present in ``rules``, in :data:`GENERIC_RULES` order."""
        ...
