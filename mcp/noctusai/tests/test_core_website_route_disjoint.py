"""Fitness test: core SPA paths and website paths never overlap.

Under the planned single-host layout (roadmap core-host-retirement-2026-11)
noctusai.com serves BOTH the prerendered website and the core SPA, so a path
claimed by both would silently shadow one of them. Sources, all parsed by AST
(ts-morph via `mcp/noctusai/node/route_paths_scan.mjs`; Python `ast` for the
backend tuple) -- never regex:

  core SPA  : products/core/frontend/src/main.tsx            (`path:` literals)
  website   : products/core/frontend/src/website/lib/routes.ts (`pt:`/`en:`)
  backend   : products/core/backend/app/routers/website_html.py::_WEBSITE_PATH_STEMS
              (hand-maintained -- NOC-REMEDIATE[website-app-path-derivation];
              this test is its drift guard until it is derived at build time)

The only documented overlap is the `/` alias (core Dashboard `/` vs website home).
Needs the node toolchain: absent => skip with a loud reason (not-run, never green).
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from node_env import node_deps_ready  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
NODE_DIR = REPO / "mcp" / "noctusai" / "node"
CORE_MAIN = REPO / "products/core/frontend/src/main.tsx"
WEBSITE_ROUTES = REPO / "products/core/frontend/src/website/lib/routes.ts"
WEBSITE_HTML_PY = REPO / "products/core/backend/app/routers/website_html.py"
DOCUMENTED_ALIASES = frozenset({"/"})


def _under(path: str, stem: str) -> bool:
    return path == stem or path.startswith(stem.rstrip("/") + "/")


def _static_head(core_path: str) -> str:
    """`/produtos/:id` -> `/produtos`; `/admin/billing/*` -> `/admin/billing`."""
    return core_path.split("/:")[0].split("/*")[0].rstrip("/") or "/"


def find_overlaps(core: list[str], website: list[dict]) -> list[str]:
    """Core paths that equal or nest with a website path (either way), minus aliases."""
    out: list[str] = []
    for c in core:
        if c in DOCUMENTED_ALIASES:
            continue
        ch = _static_head(c)
        for w in website:
            wp = w["path"].rstrip("/") or "/"
            if wp in DOCUMENTED_ALIASES:
                continue
            if _under(ch, wp) or _under(wp, ch):
                out.append(f"{c} <-> {w['path']}")
    return out


def find_stem_drift(stems: tuple[str, ...], website: list[dict]) -> list[str]:
    """Website routes the backend tuple does not know, and stems no route backs."""
    out = []
    for w in website:
        if w["path"] == "/":
            continue
        if not any(_under(w["path"].rstrip("/"), s) for s in stems):
            out.append(f"website route {w['path']} not covered by _WEBSITE_PATH_STEMS")
    for s in stems:
        if not any(_under(w["path"].rstrip("/"), s) for w in website):
            out.append(f"stem {s} backs no website route")
    return out


def _backend_stems() -> tuple[str, ...]:
    tree = ast.parse(WEBSITE_HTML_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_WEBSITE_PATH_STEMS" for t in node.targets
        ):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("_WEBSITE_PATH_STEMS not found in website_html.py")


@pytest.fixture(scope="module")
def scanned() -> dict:
    if not node_deps_ready(NODE_DIR, require="ts-morph"):
        pytest.skip("NOT RUN: mcp/noctusai/node/node_modules (ts-morph) not provisioned")
    proc = subprocess.run(
        ["node", str(NODE_DIR / "route_paths_scan.mjs")],
        input=json.dumps({"coreMain": str(CORE_MAIN), "websiteRoutes": str(WEBSITE_ROUTES)}),
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["core"] and data["website"], "scan returned an empty route set (parser drift?)"
    return data


# -- red/green fixtures for the detector itself -------------------------------
def test_detector_red_overlap_is_found():
    assert find_overlaps(["/precos"], [{"path": "/precos", "dynamic": False}])
    assert find_overlaps(["/produtos/:id"], [{"path": "/produtos/", "dynamic": True}])


def test_detector_green_alias_and_disjoint_pass():
    web = [{"path": "/", "dynamic": False}, {"path": "/precos", "dynamic": False}]
    assert find_overlaps(["/", "/pricing", "/team"], web) == []


def test_stem_drift_red_and_green():
    web = [{"path": "/sobre", "dynamic": False}]
    assert find_stem_drift(("/sobre",), web) == []
    assert find_stem_drift((), web)
    assert find_stem_drift(("/sobre", "/old"), web)


# -- the real tree ---------------------------------------------------------------
def test_core_and_website_paths_are_disjoint(scanned):
    assert find_overlaps(scanned["core"], scanned["website"]) == []


def test_backend_stem_tuple_matches_website_routes(scanned):
    assert find_stem_drift(_backend_stems(), scanned["website"]) == []
