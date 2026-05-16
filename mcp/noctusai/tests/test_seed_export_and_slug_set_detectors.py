"""Regression tests for the social-wiring-absorption Stage-4 codification
pair — W5.7a + W5.9a (2026-05-16).

Two detectors promoting Stage-3 methodology rules to Stage-4 keeper
detectors. Each gets a focused `Test<CamelCase>` class with
positive-fires + negative-doesn't-fire + edge-case tests. Tests are
file-system-scoped (`tmp_path` fixture) per the seed test pattern; no
monkey-patching of our own code.

Detectors covered:
  - `check_seed_export_membership`     (W5.7a; N=2: lid_auth + FE WA hooks)
  - `check_hardcoded_product_slug_set` (W5.9a; N=2: cors_registry + sentinel)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_hardcoded_product_slug_set,
    check_seed_export_membership,
)


# ---------------------------------------------------------------------------
# check_seed_export_membership
# ---------------------------------------------------------------------------


class TestCheckSeedExportMembership:
    """A symbol a product imports from the seed surface must be in that
    package's public `__all__` (backend) / `index.ts` re-exports (frontend).
    """

    def _mk_whatsapp_pkg(self, tmp_path: Path, dunder_all: str) -> None:
        """Write the `noctusai_lib.integrations.whatsapp` PACKAGE
        `__init__.py` with the given `__all__` literal — the lid_auth
        half-ship shape (package surface that omits a consumed symbol).
        """
        pkg = (
            tmp_path / "seed" / "lib" / "backend" / "noctusai_lib"
            / "integrations" / "whatsapp"
        )
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text(f"__all__ = {dunder_all}\n")
        (pkg / "lid_auth.py").write_text("def resolve_canonical_session():\n    ...\n")

    def _mk_product_backend(self, tmp_path: Path, py: str) -> None:
        app = tmp_path / "products" / "p1" / "backend" / "app"
        app.mkdir(parents=True)
        (app / "service.py").write_text(py)

    def test_flags_backend_symbol_absent_from_package_all(self, tmp_path):
        # lid_auth-shape half-ship: imported FROM THE PACKAGE but the
        # package `__all__` omits it.
        self._mk_whatsapp_pkg(tmp_path, '["WahaClient"]')
        self._mk_product_backend(
            tmp_path,
            "from noctusai_lib.integrations.whatsapp import resolve_canonical_session\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "resolve_canonical_session" in issues[0]["issue"]
        assert "__all__" in issues[0]["issue"]
        assert issues[0]["product"] == "p1"

    def test_does_not_flag_backend_symbol_in_package_all(self, tmp_path):
        self._mk_whatsapp_pkg(tmp_path, '["WahaClient", "resolve_canonical_session"]')
        self._mk_product_backend(
            tmp_path,
            "from noctusai_lib.integrations.whatsapp import resolve_canonical_session\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_plain_module_deep_import(self, tmp_path):
        """`from noctusai_lib.api.auth import make_get_current_user_org`
        where `auth` is a plain module (`auth.py`, no package `__init__`)
        is a LEGITIMATE deep import — not the half-ship rule.
        """
        api = tmp_path / "seed" / "lib" / "backend" / "noctusai_lib" / "api"
        api.mkdir(parents=True)
        (api / "auth.py").write_text("def make_get_current_user_org():\n    ...\n")
        self._mk_product_backend(
            tmp_path,
            "from noctusai_lib.api.auth import make_get_current_user_org\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_submodule_import(self, tmp_path):
        """`from noctusai_lib.api import scheduler` where `scheduler` is the
        submodule `noctusai_lib/api/scheduler.py` is a MODULE import, not a
        symbol re-export — `__all__` does not govern it. (N=4 live FP class:
        therapy/PF/mailing/social-wiring all do this.)
        """
        api = tmp_path / "seed" / "lib" / "backend" / "noctusai_lib" / "api"
        api.mkdir(parents=True)
        (api / "__init__.py").write_text('__all__ = ["StrictHttpModel"]\n')
        (api / "scheduler.py").write_text("def run():\n    ...\n")
        self._mk_product_backend(
            tmp_path,
            "from noctusai_lib.api import scheduler as seed_scheduler\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_flags_real_symbol_half_ship_not_submodule(self, tmp_path):
        """A symbol that is NOT a submodule and NOT in `__all__` still
        fires (proves the submodule guard is narrow, not a blanket mute).
        """
        api = tmp_path / "seed" / "lib" / "backend" / "noctusai_lib" / "api"
        api.mkdir(parents=True)
        (api / "__init__.py").write_text(
            '__all__ = ["StrictHttpModel"]\n'
            "def make_thing():\n    ...\n"  # defined but not in __all__
        )
        self._mk_product_backend(
            tmp_path, "from noctusai_lib.api import make_thing\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert len(issues) == 1, issues
        assert "make_thing" in issues[0]["issue"]

    def test_skips_when_package_all_non_literal(self, tmp_path):
        # Computed __all__ → conservatively skip (false negatives over noise).
        self._mk_whatsapp_pkg(tmp_path, "_BASE + ['x']")
        self._mk_product_backend(
            tmp_path,
            "from noctusai_lib.integrations.whatsapp import resolve_canonical_session\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_flags_frontend_symbol_absent_from_index(self, tmp_path):
        # createWhatsAppConnectionHooks-shape half-ship (W2.4/DEP-B).
        fe_index = tmp_path / "seed" / "lib" / "frontend" / "src"
        fe_index.mkdir(parents=True)
        (fe_index / "index.ts").write_text(
            "export { createApiClient } from './api';\n"
        )
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "useWA.ts").write_text(
            "import { createWhatsAppConnectionHooks } from '@noctusai/lib';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert len(issues) == 1, issues
        assert "createWhatsAppConnectionHooks" in issues[0]["issue"]
        assert "index.ts" in issues[0]["issue"]

    def test_does_not_flag_frontend_symbol_reexported(self, tmp_path):
        fe_index = tmp_path / "seed" / "lib" / "frontend" / "src"
        fe_index.mkdir(parents=True)
        (fe_index / "index.ts").write_text(
            "export { createWhatsAppConnectionHooks } from './whatsapp';\n"
        )
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "useWA.ts").write_text(
            "import { createWhatsAppConnectionHooks } from '@noctusai/lib';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_frontend_aliased_reexport_satisfies(self, tmp_path):
        """`export { internal as createWhatsAppConnectionHooks }` exposes the
        aliased (right-hand) name.
        """
        fe_index = tmp_path / "seed" / "lib" / "frontend" / "src"
        fe_index.mkdir(parents=True)
        (fe_index / "index.ts").write_text(
            "export { _internal as createWhatsAppConnectionHooks } from './wa';\n"
        )
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "useWA.ts").write_text(
            "import { createWhatsAppConnectionHooks } from '@noctusai/lib';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_frontend_export_star_skips(self, tmp_path):
        # Non-enumerable surface → conservatively skip.
        fe_index = tmp_path / "seed" / "lib" / "frontend" / "src"
        fe_index.mkdir(parents=True)
        (fe_index / "index.ts").write_text("export * from './everything';\n")
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "useWA.ts").write_text(
            "import { whatever } from '@noctusai/lib';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_framework_specifier_checked_against_framework_index(self, tmp_path):
        """`@noctusai/seed` resolves to the FRAMEWORK frontend index, not
        the lib index — `createProductApp` published there must NOT flag.
        """
        lib_idx = tmp_path / "seed" / "lib" / "frontend" / "src"
        lib_idx.mkdir(parents=True)
        (lib_idx / "index.ts").write_text("export { cn } from './utils';\n")
        fw_idx = tmp_path / "seed" / "framework" / "frontend" / "src"
        fw_idx.mkdir(parents=True)
        (fw_idx / "index.ts").write_text(
            "export { createProductApp } from './factory';\n"
        )
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "App.tsx").write_text(
            "import { createProductApp } from '@noctusai/seed';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_framework_specifier_flags_when_absent_from_framework_index(self, tmp_path):
        lib_idx = tmp_path / "seed" / "lib" / "frontend" / "src"
        lib_idx.mkdir(parents=True)
        # Even though lib index lists it, the framework specifier must be
        # checked against the FRAMEWORK index (which omits it).
        (lib_idx / "index.ts").write_text(
            "export { createProductApp } from './x';\n"
        )
        fw_idx = tmp_path / "seed" / "framework" / "frontend" / "src"
        fw_idx.mkdir(parents=True)
        (fw_idx / "index.ts").write_text("export { other } from './o';\n")
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "App.tsx").write_text(
            "import { createProductApp } from '@noctusai/seed';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert len(issues) == 1, issues
        assert "createProductApp" in issues[0]["issue"]
        assert "seed/framework/frontend/src/index.ts" in issues[0]["issue"]

    def test_non_seed_import_ignored(self, tmp_path):
        self._mk_whatsapp_pkg(tmp_path, '["WahaClient"]')
        self._mk_product_backend(
            tmp_path,
            "from fastapi import FastAPI\nfrom app.models import Thing\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_missing_repo_root_no_error(self, tmp_path):
        issues = check_seed_export_membership(tmp_path / "nope")
        assert issues == []


# ---------------------------------------------------------------------------
# check_hardcoded_product_slug_set
# ---------------------------------------------------------------------------


class TestCheckHardcodedProductSlugSet:
    """Seed tests must derive product sets from `parse_products_registry()`,
    never freeze a product-slug literal.
    """

    def _mk_fleet(self, tmp_path: Path, slugs: list[str]) -> None:
        for s in slugs:
            (tmp_path / "products" / s).mkdir(parents=True)

    def _mk_seed_test(self, tmp_path: Path, py: str, *, name: str = "test_x.py") -> None:
        td = tmp_path / "seed" / "lib" / "backend" / "tests" / "config"
        td.mkdir(parents=True, exist_ok=True)
        (td / name).write_text(py)

    def test_flags_frozen_slug_tuple(self, tmp_path):
        # The per_product_cors_sentinel shape (W3.5 evidence).
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform", "adconnect"])
        self._mk_seed_test(
            tmp_path,
            'PRODUCT_SLUGS = (\n'
            '    "core",\n'
            '    "erp-imobiliario",\n'
            '    "therapy-platform",\n'
            '    "adconnect",\n'
            ')\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "parse_products_registry" in issues[0]["issue"]
        assert issues[0]["product"] == "<seed-tests>"

    def test_flags_frozen_slug_set_annassign(self, tmp_path):
        self._mk_fleet(tmp_path, ["core", "personal-finance", "daily-life"])
        self._mk_seed_test(
            tmp_path,
            'SLUGS: set[str] = {"core", "personal-finance", "daily-life"}\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert len(issues) == 1, issues

    def test_does_not_flag_below_threshold(self, tmp_path):
        # 2 slugs < _SLUG_LITERAL_MIN_HITS (3) — not a product-set marker.
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        self._mk_seed_test(
            tmp_path, 'PAIR = ("core", "erp-imobiliario")\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_registry_derived(self, tmp_path):
        # The W3.5 root-fix shape: derived, no frozen literal.
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        self._mk_seed_test(
            tmp_path,
            "from noctusai_lib.config.cors_registry import parse_products_registry\n"
            "SLUGS = {e['slug'] for e in parse_products_registry()}\n",
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == [], issues

    def test_rationale_keyword_opts_out(self, tmp_path):
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        self._mk_seed_test(
            tmp_path,
            "# slug-literal-ok: this maps slug->schema, not a product set\n"
            'SCHEMA_BY_SLUG = ("core", "erp-imobiliario", "therapy-platform")\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == [], issues

    def test_non_slug_string_collection_ignored(self, tmp_path):
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        self._mk_seed_test(
            tmp_path,
            'HEADERS = ("Content-Type", "Authorization", "X-Trace-Id")\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == [], issues

    def test_no_seed_tests_dir_no_error(self, tmp_path):
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == []

    def test_no_fleet_no_error(self, tmp_path):
        self._mk_seed_test(
            tmp_path, 'X = ("core", "erp-imobiliario", "therapy-platform")\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == []
