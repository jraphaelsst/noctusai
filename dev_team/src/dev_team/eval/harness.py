"""dev_team eval harness — runs the same task across N model configs.

Public surface (consumed via ``dev_team.eval``):
    run_eval(
        task: str,
        configs: list[str],
        project: str | None = None,
        team_builder: Callable[[str], Any] | None = None,
    ) -> dict

For each config name in ``configs``:
    1. Resolve via :func:`dev_team.configs.load_config` (validates the
       schema; missing config short-circuits with an error envelope so
       the rest of the eval still runs).
    2. Build the team via ``team_builder(config_name)``. Defaults to
       :func:`dev_team.team.build_team`. Dependency injection is the
       contract per `CLAUDE.md` "no monkey-patching of our own code" —
       tests pass a stub builder; nothing in this module reaches into
       the real ``dev_team.team`` import.
    3. Run the task via ``team.run(task)``.
    4. Pull metrics from telemetry via
       :func:`dev_team.telemetry.get_metrics` (scoped to the config /
       project). Falls back to ``team.run`` payload metrics if
       telemetry returned nothing.

Returns:

    {
        "task": "<task>",
        "project": "<project|None>",
        "configs": ["default", "codex-eval", ...],
        "results_by_config": {
            "<name>": {
                "status": "ok" | "error" | "switch-not-flipped",
                "output": <string|None>,
                "total_cost_usd": <float>,
                "total_latency_ms": <int>,
                "agent_breakdown": {<agent>: {...}, ...},
                "error": <string|None>,
            },
            ...
        },
        "diff_summary": {
            "cheapest_config": "<name|None>",
            "most_expensive_config": "<name|None>",
            "fastest_config": "<name|None>",
            "outputs_identical": <bool>,
        },
    }

If ``ANTHROPIC_API_KEY`` is missing AND the config touches the
``anthropic`` provider AND no ``team_builder`` was injected, the
config's envelope is ``{"status": "switch-not-flipped", ...}`` instead
of crashing — mirrors the CLI's rc=3 contract from B1 smoke tests.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from dev_team.configs import load_config
from dev_team.telemetry import get_metrics

# Sentinel so callers can distinguish "I want the default builder" from
# "I explicitly passed None to disable". Today both behave the same; the
# sentinel lets a future flag toggle that.
_DEFAULT_BUILDER = object()


def _default_team_builder(config_name: str) -> Any:
    """Resolve the real :func:`dev_team.team.build_team` lazily.

    Lazy so eval-harness tests that inject a stub never trigger the
    agno/anthropic import path. Mirrors the lazy-attr pattern in
    ``dev_team/__init__.py``.
    """
    from dev_team.team import build_team

    return build_team(config_name)


def _config_uses_provider(config: dict[str, Any], provider: str) -> bool:
    """Return True if any agent in ``config`` is wired to ``provider``."""
    agents = config.get("agents") or {}
    for entry in agents.values():
        if isinstance(entry, dict) and entry.get("provider") == provider:
            return True
    return False


def _switch_envelope(config_name: str, reason: str) -> dict[str, Any]:
    """Standard envelope for a config we couldn't actually run."""
    return {
        "status": "switch-not-flipped",
        "output": None,
        "total_cost_usd": 0.0,
        "total_latency_ms": 0,
        "agent_breakdown": {},
        "error": reason,
        "config": config_name,
    }


def _error_envelope(config_name: str, reason: str) -> dict[str, Any]:
    return {
        "status": "error",
        "output": None,
        "total_cost_usd": 0.0,
        "total_latency_ms": 0,
        "agent_breakdown": {},
        "error": reason,
        "config": config_name,
    }


def _metrics_to_envelope(
    config_name: str,
    output: Any,
    metrics: dict[str, Any],
    latency_ms: int,
) -> dict[str, Any]:
    """Normalize telemetry metrics + run output into the result envelope."""
    agents = metrics.get("agents") or {}
    return {
        "status": "ok",
        "output": _coerce_output(output),
        "total_cost_usd": float(metrics.get("total_cost_usd") or 0.0),
        "total_latency_ms": int(metrics.get("total_latency_ms") or latency_ms),
        "agent_breakdown": dict(agents),
        "error": None,
        "config": config_name,
    }


def _coerce_output(output: Any) -> str | None:
    """Coerce an arbitrary ``team.run`` return into a string for diffing."""
    if output is None:
        return None
    if isinstance(output, str):
        return output
    # agno Team.run typically returns an object with .content; try that
    # before falling back to str().
    content = getattr(output, "content", None)
    if isinstance(content, str):
        return content
    return str(output)


def _build_diff_summary(
    results_by_config: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate cheapest / most-expensive / fastest + output-equality."""
    ok_results = {
        name: r for name, r in results_by_config.items() if r.get("status") == "ok"
    }
    cheapest: str | None = None
    most_expensive: str | None = None
    fastest: str | None = None
    if ok_results:
        cheapest = min(ok_results, key=lambda n: ok_results[n]["total_cost_usd"])
        most_expensive = max(
            ok_results, key=lambda n: ok_results[n]["total_cost_usd"]
        )
        fastest = min(ok_results, key=lambda n: ok_results[n]["total_latency_ms"])
    outputs = {r.get("output") for r in ok_results.values()}
    return {
        "cheapest_config": cheapest,
        "most_expensive_config": most_expensive,
        "fastest_config": fastest,
        "outputs_identical": len(outputs) <= 1 and bool(ok_results),
    }


def run_eval(
    task: str,
    configs: list[str],
    project: str | None = None,
    team_builder: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Execute ``task`` across each named config; return a comparison envelope.

    See module docstring for the return-shape contract.
    """
    if not isinstance(task, str) or not task.strip():
        raise ValueError("run_eval: 'task' must be a non-empty string.")
    if not isinstance(configs, list) or not configs:
        raise ValueError("run_eval: 'configs' must be a non-empty list of names.")

    builder = team_builder if team_builder is not None else _default_team_builder
    using_default_builder = team_builder is None

    results_by_config: dict[str, dict[str, Any]] = {}
    for config_name in configs:
        # 1. Load + validate config (missing config = error envelope, not crash).
        try:
            config = load_config(config_name)
        except FileNotFoundError as exc:
            results_by_config[config_name] = _error_envelope(config_name, str(exc))
            continue
        except Exception as exc:  # ConfigSchemaError or yaml error
            results_by_config[config_name] = _error_envelope(
                config_name, f"config load failed: {exc}"
            )
            continue

        # 2. API-key guard — only enforced when using the real builder.
        if (
            using_default_builder
            and _config_uses_provider(config, "anthropic")
            and not os.environ.get("ANTHROPIC_API_KEY")
        ):
            results_by_config[config_name] = _switch_envelope(
                config_name,
                "ANTHROPIC_API_KEY missing — set it in .env to flip the switch.",
            )
            continue

        # 3. Build + run.
        t0 = time.monotonic()
        try:
            team = builder(config_name)
            output = team.run(task)
        except NotImplementedError as exc:
            # Real build_team is a B1 stub; this is the expected pre-E
            # state. Surface as switch-not-flipped, not as a hard error.
            results_by_config[config_name] = _switch_envelope(
                config_name,
                f"team builder not yet implemented: {exc}",
            )
            continue
        except Exception as exc:
            results_by_config[config_name] = _error_envelope(
                config_name, f"team.run raised: {exc!r}"
            )
            continue
        latency_ms = int((time.monotonic() - t0) * 1000)

        # 4. Pull telemetry rollup. Scope = project when supplied, else
        #    config_name so per-config eval rollups don't bleed.
        scope = project if project else config_name
        try:
            metrics = get_metrics(scope=scope) or {}
        except Exception as exc:  # telemetry must never crash the eval
            metrics = {"_telemetry_error": str(exc)}

        results_by_config[config_name] = _metrics_to_envelope(
            config_name, output, metrics, latency_ms
        )

    return {
        "task": task,
        "project": project,
        "configs": list(configs),
        "results_by_config": results_by_config,
        "diff_summary": _build_diff_summary(results_by_config),
    }


__all__ = ["run_eval"]
