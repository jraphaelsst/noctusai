"""Which Grupo OLX portal did this lead come from?

Today: **we do not know, and this module refuses to guess.**

One webhook carries ZAP, VivaReal, OLX and — once the advertiser requests
an activation code — ImovelWeb and Casa Mineira. `lead_sources` already
has a slug for each. What the payload does NOT carry is a portal name:
`leadOrigin` is `"Grupo OLX"` (or `"MCMV_OLX"`, a Minha-Casa-Minha-Vida
simulation, which is a PROGRAM and not a portal). So every lead is
attributed to the single `grupo-olx` slug.

This module exists so that stops being a code change.

**The mechanism ships now; the rules are data, and the rule table is
deliberately EMPTY.** When Gate 1 puts real traffic in front of us and
some field turns out to discriminate the portals, splitting becomes one
`PortalRule(...)` entry with the observation that justifies it — not a
patch to the ingest path, not a new branch in the normalizer, and not a
migration. Until then `resolve_portal_source_slug` returns `grupo-olx`
for everything, which is the honest answer.

Why bother before we know the discriminator: the alternative is that the
day we learn it, someone edits the attribution path under time pressure
with real leads flowing. The seam is the cheap half; the knowledge is the
expensive half. Ship the cheap half early.

🔴 **A rule requires evidence.** `PortalRule.evidence` is not
documentation — it is validated non-empty at construction, because the
whole failure mode this guards against is a plausible-looking guess
becoming permanent Portal ROI attribution. "The docs imply X" is not
evidence; "observed on delivery <id>, <date>, field=<value>" is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .normalizers import OLX_SOURCE_SLUG
from .types import OlxLead

__all__ = [
    "GRUPO_OLX_PORTAL_SLUGS",
    "OLX_PORTAL_RULES",
    "PortalAttribution",
    "PortalRule",
    "resolve_portal_source_slug",
]

#: The canonical `lead_sources` slugs a Grupo OLX lead could legitimately
#: be split into, plus the umbrella it defaults to. These already exist as
#: attribution labels for spreadsheet-imported leads, so a split reuses
#: them rather than inventing a parallel set.
GRUPO_OLX_PORTAL_SLUGS: frozenset[str] = frozenset(
    {OLX_SOURCE_SLUG, "zap", "viva-real", "imovel-web", "olx", "casa-mineira"}
)


@dataclass(frozen=True)
class PortalRule:
    """"When `field` looks like this, the lead came from `slug`."

    `field` is read from the lead's RAW vendor body first (dotted paths
    supported, e.g. `extraData.leadType`) and falls back to an `OlxLead`
    attribute, so a rule can key on something the parser does not model
    yet — which is the likely case for whatever we discover at Gate 1.

    Exactly one of `equals` / `contains` must be set. `contains` is
    case-insensitive; `equals` is exact, because a portal name arriving in
    a stable field is worth matching strictly.
    """

    slug: str
    field: str
    evidence: str
    equals: Optional[str] = None
    contains: Optional[str] = None

    def __post_init__(self) -> None:
        if self.slug not in GRUPO_OLX_PORTAL_SLUGS:
            raise ValueError(
                f"PortalRule: {self.slug!r} is not a known Grupo OLX portal slug. "
                f"Known: {sorted(GRUPO_OLX_PORTAL_SLUGS)}. Attributing to a slug "
                "that has no `lead_sources` row would drop the lead out of Portal "
                "ROI silently."
            )
        if not self.field.strip():
            raise ValueError("PortalRule: `field` is required")
        if (self.equals is None) == (self.contains is None):
            raise ValueError(
                "PortalRule: set exactly one of `equals` / `contains` "
                f"(slug={self.slug!r}, field={self.field!r})"
            )
        if not self.evidence.strip():
            raise ValueError(
                "PortalRule: `evidence` is required and must be an OBSERVATION — "
                "which delivery, when, and what the field actually held. A rule "
                "justified by a guess becomes permanent, wrong attribution in "
                "Portal ROI, and nothing downstream can tell it from a fact."
            )


@dataclass(frozen=True)
class PortalAttribution:
    """The resolved slug plus WHY, so a surprising attribution is
    traceable to the rule that caused it instead of being folklore."""

    slug: str
    rule: Optional[PortalRule] = None

    @property
    def is_split(self) -> bool:
        """True when a rule fired, i.e. this is not the umbrella default."""
        return self.rule is not None


#: 🔴 EMPTY ON PURPOSE — see the module docstring. Nothing in the vendor
#: documentation distinguishes the portals, so there is no honest rule to
#: write yet. Gate 1 fills this from observed traffic.
OLX_PORTAL_RULES: tuple[PortalRule, ...] = ()


def _read_field(lead: OlxLead, field: str) -> Optional[Any]:
    """Raw body first (dotted path), then the parsed `OlxLead` attribute.

    Raw wins because a Gate-1 discriminator is most likely a key the
    parser does not model — and a rule must be writable the moment the key
    is observed, without a parser change first.
    """
    node: Any = lead.raw if isinstance(lead.raw, dict) else {}
    for part in field.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            node = None
            break
    if node is not None:
        return node
    return getattr(lead, field, None)


def _matches(rule: PortalRule, value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    if rule.equals is not None:
        return text == rule.equals
    return rule.contains is not None and rule.contains.lower() in text.lower()


def resolve_portal_source_slug(
    lead: OlxLead,
    *,
    rules: tuple[PortalRule, ...] = OLX_PORTAL_RULES,
) -> PortalAttribution:
    """The `lead_sources` slug this lead should be attributed to.

    First matching rule wins (order is precedence). No match — which is
    every lead today — returns the `grupo-olx` umbrella. Never raises:
    attribution must not be able to reject a real lead.
    """
    for rule in rules:
        if _matches(rule, _read_field(lead, rule.field)):
            return PortalAttribution(slug=rule.slug, rule=rule)
    return PortalAttribution(slug=OLX_SOURCE_SLUG)
