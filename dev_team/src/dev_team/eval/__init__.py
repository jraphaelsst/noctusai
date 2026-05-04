"""dev_team eval harness — runs the same task across N model configs and
records timing + cost + output diffs into the telemetry store.

Public surface (contract):
    run_eval(task: str, configs: list[str], project: str | None = None) -> dict

Stub raises NotImplementedError until D engineer ships harness.py.
"""

from __future__ import annotations

try:  # pragma: no cover
    from dev_team.eval.harness import run_eval  # type: ignore
except ImportError:

    def run_eval(*args, **kwargs):  # type: ignore[no-redef]
        raise NotImplementedError(
            "run_eval not wired yet — D engineer ships eval/harness.py"
        )


__all__ = ["run_eval"]
