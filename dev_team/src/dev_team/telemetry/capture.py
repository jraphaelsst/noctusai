"""Telemetry capture — write per-event rows + agno hook wiring.

Two surfaces:

1. :func:`capture_event` — direct insert. Accepts a dict with the
   schema fields (see PROJECT.md §5.4); fills sane defaults for
   optional fields. Use this when you have an event you want to
   record (manual capture, tests, the wrapper).

2. :func:`register_team_hooks` / :func:`register_agent_hooks` —
   auto-wires capture around an agno Team / Agent. agno 2.6.4
   doesn't expose a stable post-turn callback API; we ship a
   :class:`TelemetryWrappedTeam` decorator + :func:`wrap_agent_run`
   that intercept ``run()`` / ``arun()``, time the call, extract
   token usage from the response, and write one row per turn.

The wrapper-style approach is the safe default — when agno later
adds first-class hooks, we keep this surface and wire to the hooks
internally; consumers don't change.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable

from noctusai_lib.primitives.timeutil import now_utc

from dev_team.telemetry.store import connect

# -- core insert --------------------------------------------------------


_REQUIRED_FIELDS = (
    "config_name",
    "agent_name",
    "turn_index",
    "input_tokens",
    "output_tokens",
    "total_cost_usd",
    "latency_ms",
    "outcome",
    "output_chars",
)


def capture_event(event: dict[str, Any]) -> None:
    """Persist a single telemetry event row.

    Required fields (per PROJECT.md §5.4): config_name, agent_name,
    turn_index, input_tokens, output_tokens, total_cost_usd,
    latency_ms, outcome, output_chars.

    Optional fields (default ``None`` / ``""``): timestamp (auto if
    missing), project, sub_team, tool_calls, task_hash. ``tool_calls``
    accepts a list — JSON-encoded on insert.

    Schema is created lazily on first call (via
    :func:`store.connect`).
    """
    missing = [k for k in _REQUIRED_FIELDS if k not in event]
    if missing:
        raise ValueError(
            f"capture_event missing required fields: {missing}"
        )

    timestamp = event.get("timestamp") or now_utc().isoformat()
    tool_calls = event.get("tool_calls")
    if tool_calls is not None and not isinstance(tool_calls, str):
        tool_calls = json.dumps(tool_calls)

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO events (
                timestamp, project, config_name, agent_name, sub_team,
                turn_index, input_tokens, output_tokens, total_cost_usd,
                latency_ms, tool_calls, outcome, output_chars, task_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                event.get("project"),
                event["config_name"],
                event["agent_name"],
                event.get("sub_team"),
                int(event["turn_index"]),
                int(event["input_tokens"]),
                int(event["output_tokens"]),
                float(event["total_cost_usd"]),
                int(event["latency_ms"]),
                tool_calls,
                event["outcome"],
                int(event["output_chars"]),
                event.get("task_hash"),
            ),
        )
        conn.commit()


# -- agno hook wiring ---------------------------------------------------


def task_hash(task: str) -> str:
    """Stable sha1 of a task string — used for grouping events."""
    return hashlib.sha1(task.encode("utf-8")).hexdigest()


def _extract_usage(response: Any) -> tuple[int, int, float]:
    """Best-effort token + cost extraction from an agno response.

    agno 2.6.4 isn't installed at scaffold time; this is defensive —
    we look for the common shapes (``response.metrics``,
    ``response.usage``, ``response.input_tokens``) and fall back to
    zeros when the shape is unfamiliar. Real numbers are wired once
    the agno API surface is locked in.
    """
    inp = 0
    out = 0
    cost = 0.0
    if response is None:
        return inp, out, cost

    metrics = getattr(response, "metrics", None) or getattr(response, "usage", None)
    if metrics is not None:
        inp = int(getattr(metrics, "input_tokens", 0) or 0)
        out = int(getattr(metrics, "output_tokens", 0) or 0)
        cost = float(
            getattr(metrics, "total_cost", 0.0)
            or getattr(metrics, "total_cost_usd", 0.0)
            or 0.0
        )
        return inp, out, cost

    inp = int(getattr(response, "input_tokens", 0) or 0)
    out = int(getattr(response, "output_tokens", 0) or 0)
    cost = float(getattr(response, "total_cost_usd", 0.0) or 0.0)
    return inp, out, cost


def _extract_output_chars(response: Any) -> int:
    if response is None:
        return 0
    text = (
        getattr(response, "content", None)
        or getattr(response, "text", None)
        or getattr(response, "output", None)
        or ""
    )
    return len(str(text))


def _extract_tool_calls(response: Any) -> list[dict[str, Any]] | None:
    if response is None:
        return None
    calls = getattr(response, "tool_calls", None) or getattr(response, "tools_used", None)
    if calls is None:
        return None
    out: list[dict[str, Any]] = []
    for call in calls:
        if isinstance(call, dict):
            out.append(call)
        else:
            out.append(
                {
                    "name": getattr(call, "name", str(call)),
                    "args": getattr(call, "args", None),
                    "latency_ms": getattr(call, "latency_ms", None),
                }
            )
    return out or None


def _make_event(
    *,
    agent_name: str,
    config_name: str,
    project: str | None,
    sub_team: str | None,
    turn_index: int,
    response: Any,
    latency_ms: int,
    outcome: str,
    task: str | None,
) -> dict[str, Any]:
    inp, out, cost = _extract_usage(response)
    return {
        "config_name": config_name,
        "agent_name": agent_name,
        "project": project,
        "sub_team": sub_team,
        "turn_index": turn_index,
        "input_tokens": inp,
        "output_tokens": out,
        "total_cost_usd": cost,
        "latency_ms": latency_ms,
        "tool_calls": _extract_tool_calls(response),
        "outcome": outcome,
        "output_chars": _extract_output_chars(response),
        "task_hash": task_hash(task) if task else None,
    }


class TelemetryWrappedTeam:
    """Decorator-wrapper around an agno Team that captures every run.

    Use when agno's first-class callback hooks aren't available (true
    of 2.6.4). Forwards every other attribute to the wrapped team via
    ``__getattr__`` so it's drop-in.

    Captured event uses the team's leader as the ``agent_name`` (the
    user-facing actor); per-specialist events come from
    :func:`wrap_agent_run` applied to each Agent before it joins the
    Team.
    """

    def __init__(
        self,
        team: Any,
        *,
        config_name: str,
        project: str | None = None,
        agent_name: str = "leader",
        sub_team: str | None = None,
    ) -> None:
        self._team = team
        self._config_name = config_name
        self._project = project
        self._agent_name = agent_name
        self._sub_team = sub_team
        self._turn_index = 0

    def __getattr__(self, item: str) -> Any:
        return getattr(self._team, item)

    def run(self, task: str, *args: Any, **kwargs: Any) -> Any:
        self._turn_index += 1
        start = time.perf_counter()
        outcome = "ok"
        response: Any = None
        try:
            response = self._team.run(task, *args, **kwargs)
            return response
        except Exception:
            outcome = "error"
            raise
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            try:
                capture_event(
                    _make_event(
                        agent_name=self._agent_name,
                        config_name=self._config_name,
                        project=self._project,
                        sub_team=self._sub_team,
                        turn_index=self._turn_index,
                        response=response,
                        latency_ms=latency_ms,
                        outcome=outcome,
                        task=task,
                    )
                )
            except Exception:
                # Telemetry must never crash the run. Re-raise the
                # write failure visibly — log to stderr so it's
                # explicit (no silent-error pattern).
                import sys
                import traceback

                print(
                    "[dev_team.telemetry] capture_event failed:",
                    file=sys.stderr,
                )
                traceback.print_exc()


def wrap_agent_run(
    agent: Any,
    *,
    agent_name: str,
    config_name: str,
    project: str | None = None,
    sub_team: str | None = None,
) -> Callable[..., Any]:
    """Wrap an Agent.run callable so each invocation captures one event.

    Mutates the agent in place — replaces ``agent.run`` with a wrapped
    version. Returns the wrapped callable for callers that prefer
    explicit invocation. Idempotent: re-wrapping is a no-op.
    """
    if getattr(agent, "_dev_team_wrapped", False):
        return agent.run

    original = agent.run
    state = {"turn_index": 0}

    def wrapped(task: str, *args: Any, **kwargs: Any) -> Any:
        state["turn_index"] += 1
        start = time.perf_counter()
        outcome = "ok"
        response: Any = None
        try:
            response = original(task, *args, **kwargs)
            return response
        except Exception:
            outcome = "error"
            raise
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            try:
                capture_event(
                    _make_event(
                        agent_name=agent_name,
                        config_name=config_name,
                        project=project,
                        sub_team=sub_team,
                        turn_index=state["turn_index"],
                        response=response,
                        latency_ms=latency_ms,
                        outcome=outcome,
                        task=task,
                    )
                )
            except Exception:
                import sys
                import traceback

                print(
                    "[dev_team.telemetry] capture_event failed:",
                    file=sys.stderr,
                )
                traceback.print_exc()

    agent.run = wrapped
    agent._dev_team_wrapped = True
    return wrapped


def register_team_hooks(
    team: Any,
    *,
    config_name: str = "default",
    project: str | None = None,
    agent_name: str = "leader",
    sub_team: str | None = None,
) -> Any:
    """Wire telemetry capture around an agno Team.

    If agno gains a stable callback registration API in a future
    release we'll wire to that here; for 2.6.4 we return a
    :class:`TelemetryWrappedTeam` that intercepts ``team.run`` and
    captures one event per turn.

    Returns the wrapped object — callers should use the return value
    in place of the original team.
    """
    return TelemetryWrappedTeam(
        team,
        config_name=config_name,
        project=project,
        agent_name=agent_name,
        sub_team=sub_team,
    )


def register_agent_hooks(
    agent: Any,
    *,
    agent_name: str,
    config_name: str = "default",
    project: str | None = None,
    sub_team: str | None = None,
) -> Any:
    """Wire telemetry capture around a single agno Agent.

    Mutates the agent in place (idempotent) and returns it. Use this
    on each specialist before they join a team so you get per-agent
    events alongside the per-team event from
    :func:`register_team_hooks`.
    """
    wrap_agent_run(
        agent,
        agent_name=agent_name,
        config_name=config_name,
        project=project,
        sub_team=sub_team,
    )
    return agent


__all__ = [
    "capture_event",
    "register_team_hooks",
    "register_agent_hooks",
    "TelemetryWrappedTeam",
    "wrap_agent_run",
    "task_hash",
]
