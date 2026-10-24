"""Every seed package the toolkit imports is installed into the toolkit venv.

2026-10-24: tools imported `noctusai_seed` (verify_db_guards -> organ guard probes) while
`requirements.txt` installed only `seed/lib/backend`. The CLI self-execs a bare `python` into
`mcp/noctusai/.venv`, so the SAME check passed from `./venv/bin/python` and came back
"blocked (unverified)" for every product from `python` or the MCP server. The verdict depended
on the launching interpreter; this pins the cause statically (the environment is never
consulted: an env that happens to have the package is how it stayed invisible).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[1]
REPO = TOOLKIT.parents[1]


def _seed_packages() -> dict[str, str]:
    """``{import_name: "seed/<x>/backend"}`` for every seed python package."""
    out = {}
    for pyproject in sorted((REPO / "seed").glob("*/backend/pyproject.toml")):
        backend = pyproject.parent
        for pkg in backend.iterdir():
            if pkg.is_dir() and (pkg / "__init__.py").is_file() and pkg.name.startswith("noctusai_"):
                out[pkg.name] = str(backend.relative_to(REPO))
    return out


def _imported_top_levels() -> dict[str, str]:
    """``{top_level_module: first_file}`` over the toolkit's own python sources."""
    seen: dict[str, str] = {}
    for path in sorted(TOOLKIT.rglob("*.py")):
        rel = path.relative_to(TOOLKIT)
        if rel.parts[0] in {".venv", "tests"} or "node_modules" in rel.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module]
            for name in names:
                seen.setdefault(name.split(".", 1)[0], str(rel))
    return seen


def _editable_installs() -> set[str]:
    reqs = (TOOLKIT / "requirements.txt").read_text(encoding="utf-8")
    return {
        str((TOOLKIT / m.group(1)).resolve().relative_to(REPO))
        for m in re.finditer(r"^-e\s+(\S+)", reqs, re.MULTILINE)
    }


def test_every_imported_seed_package_is_an_editable_install():
    seed = _seed_packages()
    installed = _editable_installs()
    missing = {
        mod: (seed[mod], where) for mod, where in _imported_top_levels().items()
        if mod in seed and seed[mod] not in installed
    }
    assert not missing, (
        "toolkit imports a seed package its venv never installs "
        "(add `-e ../../<path>` to mcp/noctusai/requirements.txt): "
        + ", ".join(f"{m} ({path}, first used in {where})" for m, (path, where) in sorted(missing.items()))
    )


def test_the_known_seed_packages_are_found():
    seed = _seed_packages()
    assert seed.get("noctusai_lib") == "seed/lib/backend"
    assert seed.get("noctusai_seed") == "seed/framework/backend"
