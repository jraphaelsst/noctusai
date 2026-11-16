"""ONE ordered rewrite chain for a Bash PreToolUse call (heavy-run gate + background wrapper).

WHY (2026-11-14): `heavy_run_guard` (wrap a heavy test/build run in `hw_admission.py run`) and `bg_launch_guard`
(wrap a background launch in `scripts/bg_run.py`) both answer with `updatedInput`. Claude Code runs every matching
PreToolUse hook IN PARALLEL on the ORIGINAL tool input, and when several return `updatedInput` one wins, with no
ordering guarantee: a background heavy command would lose one of its two wraps, silently. The composition is
therefore NOT left to the harness: one hook (`scripts/hooks/claude-guard-bash-rewrite.py`) calls `decide` here.

ORDER (fixed): the heavy-run wrap is INNERMOST, the bg_run wrap OUTERMOST:

    bg_run.py ... --command='<venv python> hw_admission.py run --job J --wait-s 7200 -- bash -c <cmd>'

so the process tree ends at runtime (bg_run owns the lifetime) AND the admission gate still queues the heavy work.

RULES
  * a deny from EITHER guard wins over any rewrite, and is attributed to the guard that issued it (`guard`);
  * idempotent: each member guard already skips input it wrapped (`hw_admission.py` / `bg_run.py` in the command),
    so already-wrapped input comes back unchanged and nothing is wrapped twice;
  * every applied rewrite logs its own guard event (outcome=rewrite, guard=heavy-run | background-launch);
    the returned verdict carries `events_logged` so the runner does not log a third;
  * the background guard's warn-only shadow mode is kept (`NOC_BG_LAUNCH_MODE=shadow`): its verdict is logged
    as a `warn` and ignored, the heavy-run guard still applies.
DELIBERATE LIMIT: input the agent already wrapped in `bg_run.py` is not looked into, so a heavy command inside a
hand-written wrapper is not gated (the hardware gate itself and CI remain the backstops).
KB § PATTERNS/common/background-agent-lifecycle.md · KB § PATTERNS/devops/hardware-admission-budget.md
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_HOOKS = _HERE.parents[4] / "scripts" / "hooks"
for _p in (str(_HERE), str(_HOOKS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bg_launch_guard as bg  # noqa: E402
import heavy_run_guard as heavy  # noqa: E402
from _guard_failclosed import log_event  # noqa: E402

HEAVY, BG = "heavy-run", "background-launch"
_BG_EXTRA = {"kind": "guard", "owner": "tooling-engineer"}


def _deny(guard: str, verdict: dict[str, Any]) -> dict[str, Any]:
    return {"reason": verdict["reason"], "guard": guard}


def decide(payload: dict[str, Any], *, event_log: Path | None = None) -> dict[str, Any] | None:
    """None to allow untouched; `{"reason", "guard"}` to deny; `{"decision": "allow", "updated_input", "context",
    "steps", "events_logged"}` for the composed rewrite. Only `Bash` is judged."""
    if (payload.get("tool_name") or "") != "Bash":
        return None
    ti = dict(payload.get("tool_input") or {})
    original = ti.get("command") or ""
    if not original.strip():
        return None
    steps: list[dict[str, str]] = []
    command = original

    h = heavy.decide(payload)  # 1. innermost: the hardware gate
    if h is not None:
        if h.get("decision") != "allow":
            return _deny(HEAVY, h)
        command = h["updated_input"]["command"]
        steps.append({"guard": HEAVY, "context": h.get("context", "")})

    b = bg.decide(payload)  # 2. outermost: the lifetime wrapper. Judged on what the AGENT wrote (loops, polls).
    if b is not None:
        enforcing = bg.mode() == "enforce"
        if b.get("decision") != "allow":
            if enforcing:
                return _deny(BG, b)
            why = b.get("reason", "")
            log_event(BG, "warn", why, payload, event_log, extra={**_BG_EXTRA, "source": "shadow"})
            print(f"[noc-guard:{BG}] WARNING (shadow until {bg.ENFORCE_FROM}, then enforced): {why}", file=sys.stderr)
        elif not enforcing:
            log_event(BG, "warn", f"would rewrite: {b.get('context', '')}", payload, event_log,
                      extra={**_BG_EXTRA, "source": "shadow"})
        else:
            wrapped = bg.rewrite_finite(ti, original, wrapped=command)
            command = wrapped["updated_input"]["command"]
            steps.append({"guard": BG, "context": wrapped.get("context", "")})

    if not steps:
        return None
    for s in steps:  # one rewrite event per guard that rewrote, under that guard's own name
        log_event(s["guard"], "rewrite", s["context"], payload, event_log)
    return {
        "decision": "allow",
        "updated_input": {**ti, "command": command},
        "context": " ".join(s["context"] for s in steps) + " [rewrite chain: heavy-run wrap innermost, bg_run outermost]",
        "steps": steps,
        "events_logged": True,
    }
