"""noctus.dev.scaffold_keeper — emit a Stage-4 keeper as consumable
code: the `check_<name>` detector + colocated `Test<CamelCase>` + the
cli `--check-*` block + the pre-commit gate block.

Makes the codification pipeline's Stage-4 a tool, not a ritual
(check_files_outlined was hand-built end-to-end this session). Returns
code (does not edit the 6k-line compliance.py programmatically) —
agent pastes the detector before `def register`.
"""
from __future__ import annotations


def scaffold_keeper(name: str, flag: str, severity: str = "high") -> dict:
    """`name` = snake detector noun (no `check_` prefix); `flag` = the
    cli `--check-<flag>`. Returns detector/test/cli/precommit code."""
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
    precommit_block = f'''# ─── Keeper: {name} (blocking) ───
STAGED_X=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null | grep -E 'TODO-pattern' || true)
if [[ -n "$STAGED_X" ]]; then
    "$PY" "$REPO_ROOT/mcp/noctusai/cli.py" --check-{flag} || {{ echo "[pre-commit] {name} FAILED." >&2; exit 1; }}
fi'''
    return {
        "ok": True,
        "detector_code": detector,
        "test_code": test,
        "test_path": f"mcp/noctusai/tests/test_{name}.py",
        "cli_argparse_line": argparse_line,
        "cli_dispatch_block": cli_block,
        "precommit_block": precommit_block,
        "note": (
            f"Paste detector before `def register` in compliance.py; add "
            f"argparse line + dispatch block to cli.py; add the pre-commit "
            f"block to scripts/pre-commit; three-way-sync the rule "
            f"(KB+CLAUDE+memory) per the codification pipeline."
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_keeper",
        description=(
            "Emit a Stage-4 keeper as consumable code: check_<name> "
            "detector + colocated Test<CamelCase> + cli --check-<flag> "
            "argparse+dispatch + pre-commit gate block. Makes Stage-4 a "
            "tool not a ritual. Returns code; agent pastes + fills the "
            "predicate + three-way-syncs the rule."
        ),
    )
    def _scaffold_keeper(name: str, flag: str, severity: str = "high") -> dict:
        return scaffold_keeper(name, flag, severity=severity)


__all__ = ["scaffold_keeper", "register"]
