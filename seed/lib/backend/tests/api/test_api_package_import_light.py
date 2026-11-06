"""`noctusai_lib.api` must stay import-light for stdlib-only submodules.

The transcriber image ships no PyJWT; `noctusai_lib.api.access_tiers` is
deliberately stdlib-only, so importing it must not drag in `api.auth`
(jwt, fastapi, licensing) via the package `__init__`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

# Resolve the package from THIS checkout, not whichever editable install wins.
_BACKEND_ROOT = str(Path(__file__).resolve().parents[2])

_BLOCK_JWT = textwrap.dedent(
    """
    import importlib.abc, sys

    class _BlockJwt(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name == "jwt" or name.startswith("jwt."):
                raise ModuleNotFoundError("No module named 'jwt'", name="jwt")
            return None

    sys.meta_path.insert(0, _BlockJwt())
    """
)


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _BLOCK_JWT + textwrap.dedent(code)],
        capture_output=True,
        env={**os.environ, "PYTHONPATH": _BACKEND_ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")},
        text=True,
        timeout=120,
    )


def test_import_access_tiers_without_jwt() -> None:
    r = _run("import noctusai_lib.api.access_tiers as m; assert m.access_tier")
    assert r.returncode == 0, r.stderr


def test_from_api_import_access_tiers_without_jwt() -> None:
    r = _run("from noctusai_lib.api import access_tiers; assert access_tiers.access_tier")
    assert r.returncode == 0, r.stderr


def test_jwt_blocker_is_effective() -> None:
    # Guards the harness: the blocker must really make jwt unimportable.
    r = _run("import jwt")
    assert r.returncode != 0 and "jwt" in r.stderr


def test_lazy_names_still_resolve() -> None:
    from noctusai_lib import api

    for name in api.__all__:
        assert getattr(api, name) is not None, name
    from noctusai_lib.api import AuthContext, StrictHttpModel  # noqa: F401
