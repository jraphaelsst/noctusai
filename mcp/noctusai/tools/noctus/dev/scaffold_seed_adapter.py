"""noctus.dev.scaffold_seed_adapter — emit the canonical seed IO-module
shape (Protocol + Fake + Real + factory + types + __init__ + test) as
consumable code.

This is the CLAUDE.md §1-mandated `noctusai_lib/integrations/<x>` shape
(seed-fake-real-adapter KB pattern). GMAIL-LIB built all 6 files by
hand; every future integration rebuilds the same rigid skeleton.
Highest single token + correctness win. Returns code (agent places
the files under seed/lib/backend/noctusai_lib/integrations/<name>/).
"""
from __future__ import annotations


def scaffold_seed_adapter(name: str, methods: list[str] | None = None) -> dict:
    """`name` = package slug; `methods` = async method names the
    Protocol/Fake/Real expose. Returns `{files: {relpath: code}}`."""
    methods = methods or ["do_thing"]
    Cls = "".join(p.capitalize() for p in name.split("_"))

    def _sig(m: str) -> str:
        return f"async def {m}(self, *args, **kwargs)"

    proto_methods = "\n".join(
        f"    {_sig(m)} -> Any: ...  # TODO: real signature + docstring (quota/scopes)"
        for m in methods
    )
    fake_methods = "\n".join(
        f"    {_sig(m)}:\n        # TODO: deterministic in-memory behavior; record on self\n        return None"
        for m in methods
    )
    real_methods = "\n".join(
        f"    {_sig(m)}:\n        # TODO: real IO; log HTTP errors at WARN before re-raise; never swallow\n        raise NotImplementedError"
        for m in methods
    )

    files = {
        "types.py": (
            "from __future__ import annotations\n\n"
            "from dataclasses import dataclass\n\n\n"
            "@dataclass(frozen=True)\nclass " + Cls + "Item:\n"
            "    id: str  # TODO: value object fields\n"
        ),
        "protocol.py": (
            "from __future__ import annotations\n\n"
            "from typing import Any, Protocol\n\n\n"
            f"class {Cls}Client(Protocol):\n"
            f'    """TODO contract. Document quota/scopes per method."""\n\n'
            f"{proto_methods}\n"
        ),
        "fake.py": (
            "from __future__ import annotations\n\n"
            "from typing import Any\n\n"
            "from .protocol import " + Cls + "Client\n\n\n"
            f"class Fake{Cls}Client:\n"
            f'    """Deterministic in-memory; dev/test default."""\n\n'
            f"    def __init__(self) -> None:\n        self.calls: list = []\n\n"
            f"{fake_methods}\n"
        ),
        "real.py": (
            "from __future__ import annotations\n\n"
            "import logging\nfrom typing import Any\n\n"
            "logger = logging.getLogger(__name__)\n\n\n"
            f"class Real{Cls}Client:\n"
            f"    def __init__(self, *, api_key: str | None = None, oauth_credentials: Any = None) -> None:\n"
            f"        self._api_key = api_key\n        self._oauth = oauth_credentials\n\n"
            f"{real_methods}\n"
        ),
        "factory.py": (
            "from __future__ import annotations\n\n"
            "from typing import Any\n\n"
            "from .fake import Fake" + Cls + "Client\n"
            "from .real import Real" + Cls + "Client\n"
            "from .protocol import " + Cls + "Client\n\n\n"
            f"def make_{name}_client(*, use_fake: bool = False, api_key: str | None = None, "
            f"oauth_credentials: Any = None) -> {Cls}Client:\n"
            f"    if use_fake or (api_key is None and oauth_credentials is None):\n"
            f"        return Fake{Cls}Client()\n"
            f"    return Real{Cls}Client(api_key=api_key, oauth_credentials=oauth_credentials)\n"
        ),
        "__init__.py": (
            f'"""{name} integration — canonical Protocol+Fake+Real+factory '
            f'(seed-fake-real-adapter KB pattern). TODO: what ships / auth / consumer recipe."""\n'
            f"from .factory import make_{name}_client\n"
            f"from .fake import Fake{Cls}Client\n"
            f"from .protocol import {Cls}Client\n"
            f"from .real import Real{Cls}Client\n"
            f"from .types import {Cls}Item\n\n"
            f'__all__ = ["make_{name}_client", "Fake{Cls}Client", '
            f'"{Cls}Client", "Real{Cls}Client", "{Cls}Item"]\n'
        ),
    }
    test_code = (
        f'"""Canonical adapter tests for noctusai_lib.integrations.{name}."""\n'
        f"from noctusai_lib.integrations.{name} import make_{name}_client, Fake{Cls}Client\n\n\n"
        f"def test_factory_defaults_to_fake():\n"
        f"    assert isinstance(make_{name}_client(), Fake{Cls}Client)\n\n\n"
        f"def test_factory_real_when_creds():\n"
        f'    c = make_{name}_client(api_key="k")\n'
        f"    assert not isinstance(c, Fake{Cls}Client)\n"
    )
    return {
        "ok": True,
        "files": files,
        "test_file": f"seed/lib/backend/tests/integrations/{name}/test_{name}.py",
        "test_code": test_code,
        "dest_dir": f"seed/lib/backend/noctusai_lib/integrations/{name}/",
        "note": "Place files under dest_dir; fill TODOs (real signatures, IO, value objects); colocate the test.",
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_seed_adapter",
        description=(
            "Emit the CLAUDE.md §1-mandated seed IO-module shape "
            "(Protocol+Fake+Real+factory+types+__init__ + canonical "
            "test) as consumable code for noctusai_lib/integrations/"
            "<name>/. Highest single token+correctness win — the Fake+"
            "Real+factory rule made physical. Returns code; agent places "
            "+ fills the real signatures/IO."
        ),
    )
    def _scaffold_seed_adapter(name: str, methods: list[str] | None = None) -> dict:
        return scaffold_seed_adapter(name, methods=methods)


__all__ = ["scaffold_seed_adapter", "register"]
