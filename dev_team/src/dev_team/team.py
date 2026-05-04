"""dev_team Team factory — assembles the 11 specialists into the
coordinate-mode dev_team and instantiates the 3 collaborate-mode
sub-teams.

Public surface (contract):
    build_team(config_name: str = "default") -> agno.team.Team
    recommend_route(task: str) -> dict   # team-vs-direct heuristic

Stub raises NotImplementedError on build_team; recommend_route returns
a default until E engineer ships the heuristic.
"""

from __future__ import annotations


def build_team(config_name: str = "default"):
    """Assemble the dev_team. Returns an agno Team in coordinate mode.

    Stub — E engineer ships the real implementation in this same file.
    """
    raise NotImplementedError(
        "build_team is shipped by the team-assembly engineer (E). "
        "Stub raised so cli --dry-run is the only working dispatch path until then."
    )


def recommend_route(task: str) -> dict[str, str]:
    """Decide whether to invoke the team or stay direct (Claude Code).

    Heuristic per design-reference.md §7. Stub returns a permissive
    default; E engineer ships the actual rules.
    """
    cheap_signals = ("typo", "rename", "format", "one-line", "doc tweak")
    if any(sig in task.lower() for sig in cheap_signals):
        return {
            "recommended": "direct",
            "rationale": "Trivial / one-shot signal in task description; route to Claude Code direct.",
        }
    return {
        "recommended": "team",
        "rationale": "Default route — E engineer's heuristic will refine this.",
    }


__all__ = ["build_team", "recommend_route"]
