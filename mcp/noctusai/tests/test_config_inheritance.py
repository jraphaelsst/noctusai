"""Tests for `check_config_extends_product_settings` — the keeper detector
that flags products extending `BaseAppSettings` directly instead of
`noctusai_seed.ProductSettings`. Prevents recurrence of the 2026-04-25
core login regression where a hand-rolled env_file path resolved to a
nonexistent directory.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_config_extends_product_settings
from tools.noctus.dev.product_scope import filter_active

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"


def _write_product_config(tmp_path: Path, source: str) -> Path:
    """Lay out a fake product with `backend/app/config.py` containing `source`."""
    product = tmp_path / "fake-product"
    (product / "backend" / "app").mkdir(parents=True)
    (product / "backend" / "app" / "config.py").write_text(source)
    return product


class TestCompliantProducts:
    def test_extends_product_settings_passes(self, tmp_path):
        product = _write_product_config(tmp_path, """
from noctusai_seed import ProductSettings

class Settings(ProductSettings):
    pass
""")
        assert check_config_extends_product_settings(product) == []

    def test_real_seed_product_passes(self):
        assert check_config_extends_product_settings(PRODUCTS_DIR / "seed") == []

    def test_real_core_passes_after_phase_6_fix(self):
        assert check_config_extends_product_settings(PRODUCTS_DIR / "core") == []

    def test_all_real_products_pass(self):
        # Active products only (2026-09-22) — an asleep product's config.py
        # is not being worked on; nobody is fixing a violation there.
        dirs = sorted(d for d in PRODUCTS_DIR.iterdir() if d.is_dir() and not d.name.startswith("."))
        active = set(filter_active([d.name for d in dirs], REPO_ROOT))
        for d in dirs:
            if d.name not in active:
                continue
            issues = check_config_extends_product_settings(d)
            assert issues == [], f"{d.name} flagged: {issues}"


class TestActiveScopeFiltering:
    """Proves the choke point itself (`product_scope.filter_active`) skips
    an asleep product and keeps an active one — the mechanism
    `test_all_real_products_pass` above relies on."""

    def _write_violation(self, root: Path, slug: str) -> None:
        product = root / "products" / slug
        (product / "backend" / "app").mkdir(parents=True)
        (product / "backend" / "app" / "config.py").write_text("""
from noctusai_lib.config import BaseAppSettings

class Settings(BaseAppSettings):
    pass
""")

    def test_asleep_product_is_skipped(self, tmp_path):
        self._write_violation(tmp_path, "asleep-prod")
        self._write_violation(tmp_path, "awake-prod")
        scope = tmp_path / "deploy" / "fleet" / "active-scope.txt"
        scope.parent.mkdir(parents=True, exist_ok=True)
        scope.write_text("awake-prod\n")

        active = set(filter_active(["asleep-prod", "awake-prod"], tmp_path))

        assert active == {"awake-prod"}

    def test_active_product_still_checked(self, tmp_path):
        self._write_violation(tmp_path, "awake-prod")
        scope = tmp_path / "deploy" / "fleet" / "active-scope.txt"
        scope.parent.mkdir(parents=True, exist_ok=True)
        scope.write_text("awake-prod\n")

        product = tmp_path / "products" / "awake-prod"
        active = set(filter_active(["awake-prod"], tmp_path))
        issues = check_config_extends_product_settings(product)

        assert active == {"awake-prod"}
        assert len(issues) == 1


class TestViolations:
    def test_extends_base_app_settings_directly_flagged(self, tmp_path):
        product = _write_product_config(tmp_path, """
from noctusai_lib.config import BaseAppSettings

class Settings(BaseAppSettings):
    pass
""")
        issues = check_config_extends_product_settings(product)
        assert len(issues) == 1
        assert issues[0]["product"] == "fake-product"
        assert issues[0]["file"] == "backend/app/config.py"
        assert issues[0]["severity"] == "critical"
        assert "BaseAppSettings" in issues[0]["issue"]
        assert "ProductSettings" in issues[0]["issue"]

    def test_multiple_violator_classes_each_flagged(self, tmp_path):
        product = _write_product_config(tmp_path, """
from noctusai_lib.config import BaseAppSettings

class SettingsA(BaseAppSettings):
    pass

class SettingsB(BaseAppSettings):
    pass
""")
        issues = check_config_extends_product_settings(product)
        assert len(issues) == 2

    def test_extends_both_acceptable(self, tmp_path):
        # Multiple inheritance with ProductSettings present is fine.
        product = _write_product_config(tmp_path, """
from noctusai_seed import ProductSettings
from noctusai_lib.config import BaseAppSettings

class Settings(ProductSettings, BaseAppSettings):
    pass
""")
        assert check_config_extends_product_settings(product) == []


class TestEdgeCases:
    def test_missing_config_file_skips(self, tmp_path):
        # Product without backend/app/config.py — detector returns empty.
        product = tmp_path / "no-config-product"
        (product / "backend" / "app").mkdir(parents=True)
        assert check_config_extends_product_settings(product) == []

    def test_attribute_access_base_resolved(self, tmp_path):
        # `module.BaseAppSettings` (Attribute node) — terminal name is what
        # matters; AST resolver should return "BaseAppSettings" and flag it.
        product = _write_product_config(tmp_path, """
import noctusai_lib.config as cfg

class Settings(cfg.BaseAppSettings):
    pass
""")
        issues = check_config_extends_product_settings(product)
        assert len(issues) == 1
        assert "BaseAppSettings" in issues[0]["issue"]

    def test_unrelated_class_ignored(self, tmp_path):
        # A class extending neither ProductSettings nor BaseAppSettings is
        # not a config concern — detector ignores it.
        product = _write_product_config(tmp_path, """
class SomeUnrelatedHelper:
    pass

class AnotherOne(object):
    pass
""")
        assert check_config_extends_product_settings(product) == []

    def test_syntax_error_surfaces(self, tmp_path):
        # Broken config.py — detector reports the parse failure rather than
        # silently skipping (silent-error rule).
        product = _write_product_config(tmp_path, "this is not valid python ::: ===")
        issues = check_config_extends_product_settings(product)
        assert len(issues) == 1
        assert "Failed to parse" in issues[0]["issue"]
        assert issues[0]["severity"] == "critical"
