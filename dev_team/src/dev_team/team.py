"""dev_team Team factory — assembles the 11 specialists into the
coordinate-mode dev_team and instantiates the 3 collaborate-mode
sub-teams.

Public surface (contract):
    build_team(config_name: str = "default") -> agno.team.Team
    recommend_route(task: str) -> dict   # team-vs-direct heuristic

Per design-reference.md §1.2 (structural diagram): the dev_team is a
coordinate-mode Team with the Leader + 10 specialists as members.
The 3 sub-teams (design_review_team / code_review_team /
incident_response_team) are separately assembled and invoked by the
Leader via the ``invoke_subteam`` tool — they are NOT members of the
top-level team (per agno's hybrid pattern + design-reference.md §1.1).

Design rationale for the routing heuristic in :func:`recommend_route`
lives in design-reference.md §7.
"""

from __future__ import annotations

from typing import Any, Mapping

# Routing keyword catalogs — module-level so they're cheap to inspect
# and unit-test without invoking build_team.

_TRIVIAL_SIGNALS = (
    # one-shot edits / cosmetic / formatting
    "typo",
    "rename",
    "format",
    "formatting",
    "one-line",
    "one line",
    "doc tweak",
    "docstring",
    "comment fix",
    "lint",
    "whitespace",
    "indentation",
    "single-file",
    "single file",
)

# Multi-domain / cross-cutting / high-leverage signals → team.
_TEAM_SIGNALS = (
    "design",
    "architect",
    "architecture",
    "security",
    "threat model",
    "incident",
    "outage",
    "production",
    "schema change",
    "migration",
    "new feature",
    "new product",
    "new endpoint chain",
    "ship",
    "build a",
    "build the",
    "rollout",
    "review pr",
    "code review",
    "audit",
    "phase 0",
    "cross-product",
    "cross product",
    "multi-product",
    "refactor across",
    "deploy",
    "ci/cd",
)

# Signals that specifically warrant routing through design_review_team.
_DESIGN_REVIEW_SIGNALS = (
    "design",
    "architect",
    "architecture",
    "schema change",
    "ship a new",
    "new product",
    "new feature",
    "design review",
)


def build_team(config_name: str = "default"):
    """Assemble the dev_team. Returns an agno Team in coordinate mode.

    Parameters
    ----------
    config_name
        YAML config name under ``dev_team/src/dev_team/configs/``.
        ``"default"`` resolves to the Opus-on-Leader/PM/Architect/
        Security/CodeReviewer + Sonnet-on-the-rest assignment per
        design-reference.md §9.

    Returns
    -------
    agno.team.Team
        Coordinate-mode Team with 11 members: Leader + 10 specialists.

    Notes
    -----
    Imports are LOCAL so ``import dev_team.team`` doesn't require
    agno installed. The smoke test relies on this; the real factory
    only fires when an agno-aware caller asks for the assembled team.
    """
    from agno.team import Team  # local import keeps top-level cheap

    from dev_team.agents.backend_engineer import build_backend_engineer
    from dev_team.agents.code_reviewer import build_code_reviewer
    from dev_team.agents.devops_engineer import build_devops_engineer
    from dev_team.agents.frontend_engineer import build_frontend_engineer
    from dev_team.agents.product_manager import build_product_manager
    from dev_team.agents.qa_engineer import build_qa_engineer
    from dev_team.agents.security_engineer import build_security_engineer
    from dev_team.agents.solution_architect import build_solution_architect
    from dev_team.agents.technical_writer import build_technical_writer
    from dev_team.agents.ux_designer import build_ux_designer
    from dev_team.configs import load_config
    from dev_team.leader import build_leader

    cfg = load_config(config_name)

    leader = build_leader(cfg)
    specialists = [
        build_product_manager(cfg),
        build_ux_designer(cfg),
        build_solution_architect(cfg),
        build_backend_engineer(cfg),
        build_frontend_engineer(cfg),
        build_devops_engineer(cfg),
        build_security_engineer(cfg),
        build_qa_engineer(cfg),
        build_code_reviewer(cfg),
        build_technical_writer(cfg),
    ]

    members = [leader] + specialists

    return Team(
        name="dev_team",
        members=members,
        mode="coordinate",
    )


def recommend_route(task: str) -> dict[str, Any]:
    """Decide whether to invoke the team or stay direct (Claude Code).

    Heuristic per design-reference.md §7. Three layered rules:

    1. **Trivial signals** (typo / rename / format / one-line / doc
       tweak / lint / whitespace) → ``"direct"``.
    2. **Team signals** (design / security / incident / multi-domain
       / new feature / new product / cross-product / deploy) →
       ``"team"``. When a *design* signal is present, the rationale
       names ``design_review_team`` so the Leader can route directly
       there at intake.
    3. **Default** when nothing matches → ``"direct"`` (single-domain
       work with clear scope per design-reference.md §7 row 2; the
       Leader can escalate later if cross-cutting concerns surface).

    Returns
    -------
    dict
        ``{"recommended": "team" | "direct", "rationale": str,
           "matched": list[str]}``
        ``matched`` exposes which signals fired so callers (and tests)
        can audit the decision.
    """
    if not isinstance(task, str):
        raise TypeError(
            f"recommend_route expects a string task; got {type(task).__name__}"
        )

    task_lower = task.lower()

    matched_trivial = [s for s in _TRIVIAL_SIGNALS if s in task_lower]
    matched_team = [s for s in _TEAM_SIGNALS if s in task_lower]
    matched_design = [s for s in _DESIGN_REVIEW_SIGNALS if s in task_lower]

    # Rule 1 — trivial dominates only when no team-level signals appear.
    # A task like "rename a public API across 5 services" trips both
    # 'rename' (trivial) AND 'cross-product'-shaped phrasing; the
    # latter promotes it to team work.
    if matched_trivial and not matched_team:
        return {
            "recommended": "direct",
            "rationale": (
                "Trivial / one-shot signals matched "
                f"({matched_trivial}); routing to Claude Code direct per "
                "design-reference.md §7 row 1."
            ),
            "matched": matched_trivial,
        }

    # Rule 2 — team signals.
    if matched_team:
        rationale_parts = [
            "Multi-domain / high-leverage signals matched "
            f"({matched_team}); routing to dev_team per design-reference.md §7."
        ]
        if matched_design:
            rationale_parts.append(
                f"Design signals present ({matched_design}); Leader should "
                "consider invoking design_review_team at intake."
            )
        return {
            "recommended": "team",
            "rationale": " ".join(rationale_parts),
            "matched": matched_team,
        }

    # Rule 3 — default. Single-domain / unclear → direct; Leader can
    # escalate if needed once it sees the actual scope.
    return {
        "recommended": "direct",
        "rationale": (
            "No multi-domain / high-leverage signals matched; defaulting "
            "to Claude Code direct per design-reference.md §7 row 2 "
            "(single-domain task with clear scope)."
        ),
        "matched": [],
    }


__all__ = ["build_team", "recommend_route"]
