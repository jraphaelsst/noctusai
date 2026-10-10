"""`check_not_configured_carries_marker` — synthetic trees (2026-10-10)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import compliance as c  # noqa: E402


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _tree(tmp_path: Path) -> Path:
    _w(tmp_path, "seed/lib/backend/noctusai_lib/__init__.py", "")
    _w(tmp_path, "seed/lib/backend/noctusai_lib/primitives/not_configured.py",
       "class IntegrationNotConfigured:\n    pass\n")
    _w(tmp_path, "seed/lib/backend/noctusai_lib/integrations/x.py",
       "from noctusai_lib.primitives.not_configured import IntegrationNotConfigured\n"
       "class SeedBaseNotConfigured(RuntimeError, IntegrationNotConfigured):\n    pass\n")
    return tmp_path


class TestCheckNotConfiguredCarriesMarker:
    def test_unmarked_product_class_is_a_finding(self, tmp_path):
        root = _tree(tmp_path)
        _w(root, "products/p/backend/app/svc.py", "class GatewayNaoConfigurado(RuntimeError):\n    pass\n")
        issues = c.check_not_configured_carries_marker(root)
        assert [i["product"] for i in issues] == ["p"]
        assert "GatewayNaoConfigurado" in issues[0]["issue"] and issues[0]["severity"] == "high"

    def test_direct_marker_and_dotted_base_are_clean(self, tmp_path):
        root = _tree(tmp_path)
        _w(root, "products/p/backend/app/svc.py",
           "import noctusai_lib.primitives.not_configured as nc\n"
           "class AConfigNotConfigured(RuntimeError, nc.IntegrationNotConfigured):\n    pass\n")
        assert c.check_not_configured_carries_marker(root) == []

    def test_marker_inherited_via_product_or_seed_base_is_clean(self, tmp_path):
        root = _tree(tmp_path)
        _w(root, "products/p/backend/app/svc.py",
           "from noctusai_lib.primitives.not_configured import IntegrationNotConfigured\n"
           "class PublisherNotConfigured(RuntimeError, IntegrationNotConfigured):\n    pass\n"
           "class CanalNaoConfigurado(PublisherNotConfigured):\n    pass\n"
           "from noctusai_lib.integrations.x import SeedBaseNotConfigured\n"
           "class EmailNotConfigured(SeedBaseNotConfigured):\n    pass\n")
        assert c.check_not_configured_carries_marker(root) == []

    def test_unmarked_seed_class_is_a_finding_and_tests_are_ignored(self, tmp_path):
        root = _tree(tmp_path)
        _w(root, "seed/lib/backend/noctusai_lib/integrations/y.py", "class LLMNotConfigured(Exception):\n    pass\n")
        _w(root, "products/p/backend/app/tests/test_x.py", "class FakeNotConfigured(Exception):\n    pass\n")
        issues = c.check_not_configured_carries_marker(root)
        assert [(i["product"], "LLMNotConfigured" in i["issue"]) for i in issues] == [("seed", True)]

    def test_paths_scope_to_touched_products(self, tmp_path):
        root = _tree(tmp_path)
        _w(root, "products/a/backend/app/s.py", "class ANotConfigured(Exception):\n    pass\n")
        _w(root, "products/b/backend/app/s.py", "class BNotConfigured(Exception):\n    pass\n")
        assert {i["product"] for i in c.check_not_configured_carries_marker(
            root, paths=["products/a/backend/app/s.py"])} == {"a"}
        assert {i["product"] for i in c.check_not_configured_carries_marker(root)} == {"a", "b"}

    def test_real_tree_is_clean(self):
        assert c.check_not_configured_carries_marker() == []
