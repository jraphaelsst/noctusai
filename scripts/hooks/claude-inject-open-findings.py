#!/usr/bin/env python3
"""SessionStart / SubagentStart hook -- inject the open rows of every living findings ledger for the agent's target.

UX over the Python gates, never a gate (KB § PATTERNS/common/harness-mods.md): the agent STARTS knowing the open
findings of the product / agent it is about to touch, so it builds the correct shape instead of being gated later.
Compliance-by-construction: visibility is INJECTED, not opted into -- a new `.claude/agents/*.md` gets it with zero lines
added. Target = the product(s) the worktree's branch touches (`git diff origin/dev...HEAD`), else the product of the cwd
path, else a per-product top list; plus `.claude/agents/<name>.md` edits -> scope `<name>`.

Reads `project-history/findings-ledgers.json` (the roster the tool writes) + each ledger's NDJSON. Stdlib-only; always exits 0;
prints nothing on any failure (advisory). KB § PATTERNS/common/living-findings-ledgers.md.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3}
MAX_LINES = 14


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _scopes(cwd: str | None) -> list[str]:
    scopes: list[str] = []

    def add(path: str) -> None:
        p = path.replace("\\", "/").split("/")
        s = p[1] if p[0] == "products" and len(p) > 1 else ("seed" if p[0] == "seed" else (Path(p[-1]).stem if p[:2] == [".claude", "agents"] else None))
        if s and s not in scopes:
            scopes.append(s)

    for f in (_git("diff", "--name-only", "origin/dev...HEAD") + _git("diff", "--name-only")).splitlines():
        add(f)
    if not scopes and cwd:
        try:
            add(str(Path(cwd).resolve().relative_to(ROOT)))
        except ValueError:
            pass
    return scopes


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        roster = json.loads((ROOT / "project-history" / "findings-ledgers.json").read_text(encoding="utf-8"))
        scopes = _scopes(payload.get("cwd"))
        lines: list[str] = []
        for name, info in sorted(roster.get("ledgers", {}).items()):
            p = ROOT / info["path"]
            if not p.exists():
                continue
            rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
            live = [r for r in rows if r.get("status") in ("open", "in-progress")]
            pick = [r for r in live if r.get("scope") in scopes] if scopes else []
            if not pick:
                by: dict[str, int] = {}
                for r in live:
                    by[r["scope"]] = by.get(r["scope"], 0) + 1
                top = sorted(by.items(), key=lambda kv: -kv[1])[:5]
                if top:
                    lines.append(f"[{name}] {len(live)} open; most: " + ", ".join(f"{s} {n}" for s, n in top) + f" -- {info['summary']}")
                continue
            by_class: dict[str, int] = {}
            for r in pick:
                c = r.get("class") or r.get("attribution") or r.get("section", "?")
                by_class[c] = by_class.get(c, 0) + 1
            lines.append(f"[{name}] {'/'.join(scopes)}: {len(pick)} open ({', '.join(f'{c} {n}' for c, n in sorted(by_class.items()))}) -- {info['summary']}")
            worst = sorted((r for r in pick if r.get("class") != "browser-grant"), key=lambda r: SEV.get(r.get("severity", "high"), 9))
            lines += [f"  {r['id']} [{r['severity']}] {r.get('class', '')} {r['target']}"[:170] for r in worst[:MAX_LINES]]
        if lines:
            text = ("Open findings for the product/agent you are about to touch (fix-on-contact; build the compliant shape; close via "
                    "`noctus.dev.findings_ledger`, never by hand):\n" + "\n".join(lines[:MAX_LINES + 4]))
            print(json.dumps({"hookSpecificOutput": {"hookEventName": payload.get("hook_event_name", "SessionStart"), "additionalContext": text}}))
    except Exception as exc:  # noqa: BLE001 -- advisory UX: never block a session start
        print(f"[inject-open-findings] skipped: {type(exc).__name__}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
