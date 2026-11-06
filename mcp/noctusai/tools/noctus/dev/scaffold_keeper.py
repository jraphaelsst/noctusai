"""noctus.dev.scaffold_keeper — emit a Stage-4 keeper as consumable
code: the `check_<name>` detector + colocated `Test<CamelCase>` + the
cli `--check-*` block + the pre-commit gate block.

Makes the codification pipeline's Stage-4 a tool, not a ritual
(check_files_outlined was hand-built end-to-end this session). Returns
code (does not edit the 6k-line compliance.py programmatically) —
agent pastes the detector before `def register`.

BUILD TRIAD (KB § PATTERNS/common/gate-methodology-sync.md): a gate is never
authored alone. This scaffolder REFUSES unless the caller names (a) the
CONSTRUCTION leg that makes the compliant build the default (`mechanism`: a
scaffold/template/write-path/injection/api pointer, or `none (reason)`), (b) an
`owner`, and (c) the `source` read before codifying. It emits the inventory
declaration (the meta-gate `check_gate_triad` fails without it), a WARN-first
(shadow) pre-commit block, and relies on the cli exit wrapper for telemetry
(every `--check-*` run is a gate event; walls rank in `noctus.dev.gate_alignment`).
"""
from __future__ import annotations

from .gate_alignment import mechanism_ok


def scaffold_keeper(name: str, flag: str, severity: str = "high", *,
                    mechanism: str = "", owner: str = "", source: str = "") -> dict:
    """`name` = snake detector noun (no `check_` prefix); `flag` = the
    cli `--check-<flag>`. Returns detector/test/cli/precommit code plus the
    triad declaration. Refuses without mechanism + owner + source."""
    if not mechanism_ok(mechanism):
        return {"ok": False, "error": (
            "mechanism required: point at the CONSTRUCTION leg that makes the compliant build the default "
            "(scaffold:/template:/write-path:/injection:/api:/tool: <pointer>, KB §, or a path), or "
            "'none (<reason, >=12 chars>)'. A gate ships with its mechanism "
            "(KB § PATTERNS/common/gate-methodology-sync.md).")}
    if not owner.strip():
        return {"ok": False, "error": "owner required: the agent/file that owns this gate (walls route to it)."}
    if not source.strip():
        return {"ok": False, "error": "source required: the standard/rule/paper read BEFORE codifying (cite it)."}
    fn = f"check_{name}"
    Cam = "".join(p.capitalize() for p in name.split("_"))

    detector = f'''def {fn}(paths: list[Path] | None = None, repo_root: Path | None = None) -> list[dict]:
    """Keeper: TODO one-line invariant. Return shape mirrors
    check_phase_state_consistency: [{{"file": rel, "issue": str, "severity": str}}]."""
    root = repo_root or REPO_ROOT
    issues: list[dict] = []
    # TODO: deterministic predicate over `paths` (staged) or full scan
    return issues
'''
    test = f'''"""Colocated regression test for `{fn}` (meta-detector: every
keeper ships Test<CamelCase>)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import {fn}  # noqa: E402


class Test{Cam}:
    def test_clean_case_no_issues(self, tmp_path):
        assert {fn}(paths=[], repo_root=tmp_path) == []

    def test_violation_flagged(self, tmp_path):
        pass  # TODO: construct a violating fixture, assert one {severity!r} issue
'''
    cli_block = f'''    elif args.check_{flag.replace("-", "_")}:
        from tools.noctus.dev.compliance import {fn}
        issues = {fn}()
        if not issues:
            print(f"  {{GREEN}}✓ {name} clean.{{RESET}}"); sys.exit(0)
        print(f"  {{RED}}✗ {{len(issues)}} {name} issue(s):{{RESET}}")
        for i in issues:
            print(f"    {{RED}}[{{i['severity']}}]{{RESET}} {{i['file']}} — {{i['issue']}}")
        sys.exit(1)
'''
    argparse_line = (
        f'    parser.add_argument("--check-{flag}", action="store_true", '
        f'help="Keeper: {name}. Exits 1 on any issue. Pre-commit gate.")'
    )
    precommit_block = f'''# ─── Keeper: {name} (WARN-first SHADOW — promote to blocking only after the shadow record) ───
STAGED_X=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null | grep -E 'TODO-pattern' || true)
if [[ -n "$STAGED_X" ]]; then
    "$PY" "$REPO_ROOT/mcp/noctusai/cli.py" --check-{flag} || echo "[pre-commit] WARNING (shadow): {name} — see the fix it names." >&2
fi'''
    gate_id = f"keeper:check-{flag}"
    declare_command = (
        f"python mcp/noctusai/cli.py --gate-alignment declare --gate {gate_id} "
        f"--mechanism {mechanism!r} --owner {owner!r} --placement warn"
    )
    return {
        "ok": True,
        "gate_id": gate_id,
        "declare_command": declare_command,
        "inventory_entry": {"mechanism": mechanism, "owner": owner, "source": source,
                            "placement": "warn", "new": True,
                            "shadow": {"since": "<YYYY-MM-DD>", "fires": 0, "fix_rate": None}},
        "telemetry": "automatic: cli exit wrapper logs every --check-* run to guard-events.ndjson",
        "detector_code": detector,
        "test_code": test,
        "test_path": f"mcp/noctusai/tests/test_{name}.py",
        "cli_argparse_line": argparse_line,
        "cli_dispatch_block": cli_block,
        "precommit_block": precommit_block,
        "note": (
            f"Paste detector before `def register` in compliance.py; add "
            f"argparse line + dispatch block to cli.py; add the pre-commit "
            f"block to scripts/hooks/pre-commit (shadow = warn-only); RUN `declare_command` "
            f"(check_gate_triad fails otherwise) and add a decision-matrix row; promote to blocking only "
            f"after >=7 shadow days with effective-FP <=10% (gate_alignment walls); "
            f"three-way-sync the rule (KB+CLAUDE+memory) per the codification pipeline."
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_keeper",
        description=(
            "Emit a Stage-4 keeper as consumable code: check_<name> "
            "detector + colocated Test<CamelCase> + cli --check-<flag> "
            "argparse+dispatch + pre-commit gate block. Makes Stage-4 a "
            "tool not a ritual. REQUIRES mechanism (the construction leg that makes "
            "compliance the default, or 'none (reason)'), owner and source - a gate never ships "
            "alone (build triad). Returns code + the gate-inventory declaration + a WARN-first "
            "shadow pre-commit block; agent pastes, fills the predicate, runs declare_command."
        ),
    )
    def _scaffold_keeper(name: str, flag: str, severity: str = "high", mechanism: str = "",
                         owner: str = "", source: str = "") -> dict:
        return scaffold_keeper(name, flag, severity=severity, mechanism=mechanism, owner=owner, source=source)


__all__ = ["scaffold_keeper", "register"]
