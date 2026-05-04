"""Delegation tools — `delegate(specialist, task)` + `invoke_subteam(team_name, task)`.

Per design-reference.md §3 + §2.1:
- Both are LEADER-ONLY. Specialists never delegate.
- The PermissionError fires when the caller is not ``"leader"``.

The actual routing executes via the agno team — these tools are thin
wrappers that feed the team's run-loop with a typed sub-task envelope.
"""

from __future__ import annotations

from typing import Any, Callable


def _check_leader(caller: str) -> None:
    if caller != "leader":
        raise PermissionError(
            f"delegation is leader-only; caller={caller!r} is not the team leader. "
            "Specialists request work back through the leader, not directly."
        )


def delegate(
    specialist: str,
    task: str,
    *,
    caller: str = "",
    runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Route a subtask to a specialist agent.

    Args:
        specialist: Role name (e.g. ``backend_engineer``).
        task: Sub-task description.
        caller: The role-name of the calling agent — MUST be ``"leader"``.
        runner: Optional injected runner (for tests / dependency injection).
            Signature: ``runner(specialist, task) -> result``.

    Raises:
        PermissionError: ``caller`` is not the leader.
    """
    _check_leader(caller)
    if runner is not None:
        return {"specialist": specialist, "task": task, "result": runner(specialist, task)}
    return {
        "specialist": specialist,
        "task": task,
        "status": "queued",
        "note": "no runner injected; team-level dispatch happens in leader.run loop.",
    }


def invoke_subteam(
    team_name: str,
    task: str,
    *,
    caller: str = "",
    runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Invoke a sub-team (``design_review_team`` / ``code_review_team`` / ``incident_response_team``).

    Args:
        team_name: Sub-team identifier.
        task: Description of the work for the sub-team.
        caller: MUST be ``"leader"``.
        runner: Optional injected runner.

    Raises:
        PermissionError: ``caller`` is not the leader.
    """
    _check_leader(caller)
    if runner is not None:
        return {"team": team_name, "task": task, "result": runner(team_name, task)}
    return {
        "team": team_name,
        "task": task,
        "status": "queued",
        "note": "no runner injected; team-level dispatch happens in leader.run loop.",
    }


def build_delegate_tool(*, caller: str = "leader", runner=None, **kwargs) -> Callable:
    """Return a delegate tool bound to a caller (defaults to leader)."""

    def _delegate(specialist: str, task: str) -> dict[str, Any]:
        return delegate(specialist, task, caller=caller, runner=runner)

    _delegate.__doc__ = delegate.__doc__
    return _delegate


def build_invoke_subteam_tool(*, caller: str = "leader", runner=None, **kwargs) -> Callable:
    """Return an invoke_subteam tool bound to a caller (defaults to leader)."""

    def _invoke(team_name: str, task: str) -> dict[str, Any]:
        return invoke_subteam(team_name, task, caller=caller, runner=runner)

    _invoke.__doc__ = invoke_subteam.__doc__
    return _invoke


__all__ = [
    "delegate",
    "invoke_subteam",
    "build_delegate_tool",
    "build_invoke_subteam_tool",
]
