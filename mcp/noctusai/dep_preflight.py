"""dep_preflight — keep the MCP venv in step with the manifests it runs.

🔴 WHY THIS EXISTS (2026-09-16)
------------------------------
The MCP venv installs the seed lib EDITABLE (``requirements.txt`` →
``-e ../../seed/lib/backend``). Editable installs resolve dependencies only at
install time, so when ``dev`` adds a dependency to ``seed/lib/backend/
pyproject.toml`` the source arrives with the next rebase but the package never
does. The server then crashes at startup on import — 2026-09-16:
``ModuleNotFoundError: No module named 'pillow_heif'`` (S3 imaging organs), five
failed reconnects in a row. A git hook cannot close this: the primary ``dev``
checkout advances by rebase (``task_branch``/``branch_pointer``), which never
fires ``post-merge``. Server startup is the one seam every path crosses.

What it does: compare the declared ``[project].dependencies`` of the manifests
below against the venv (``importlib.metadata``, no network). Anything missing
or out of range is logged at WARNING and installed with this interpreter's pip
(only the declared specs — exactly what ``pip install -r requirements.txt``
would do). A failed install is logged at ERROR with the manual command; the
server still starts so the failure surfaces as a real traceback, never a
silent skip. ``NOCTUS_MCP_DEP_AUTOSYNC=0`` reports without installing.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement

MANIFESTS = (
    Path("seed/lib/backend/pyproject.toml"),
    Path("mcp/noctusai/pyproject.toml"),
)
INSTALL_TIMEOUT_S = 120


def unsatisfied_requirements(repo_root: Path) -> list[str]:
    """Declared requirement specs the running interpreter does not satisfy."""
    out: list[str] = []
    for rel in MANIFESTS:
        path = repo_root / rel
        with path.open("rb") as fh:
            specs = tomllib.load(fh)["project"]["dependencies"]
        for spec in specs:
            try:
                req = Requirement(spec)
            except InvalidRequirement:
                out.append(spec)  # let pip report it loudly
                continue
            if req.marker is not None and not req.marker.evaluate():
                continue
            try:
                installed = version(req.name)
            except PackageNotFoundError:
                out.append(spec)
                continue
            if req.specifier and not req.specifier.contains(installed, prereleases=True):
                out.append(spec)
    return sorted(set(out))


def ensure_declared_deps(repo_root: Path, logger: logging.Logger) -> list[str]:
    """Install any unsatisfied declared deps; return the specs that were missing."""
    missing = unsatisfied_requirements(repo_root)
    if not missing:
        return []
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *missing]
    logger.warning("dep_preflight: venv is missing declared deps: %s", ", ".join(missing))
    if os.environ.get("NOCTUS_MCP_DEP_AUTOSYNC", "1") != "1":
        logger.error("dep_preflight: autosync disabled — run: %s", " ".join(cmd))
        return missing
    try:
        r = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        logger.error("dep_preflight: install timed out after %ss — run: %s",
                     INSTALL_TIMEOUT_S, " ".join(cmd))
        return missing
    if r.returncode != 0:
        logger.error("dep_preflight: install failed (rc=%s) — run: %s\n%s",
                     r.returncode, " ".join(cmd), r.stderr[-2000:])
    else:
        logger.warning("dep_preflight: installed %s", ", ".join(missing))
    return missing
