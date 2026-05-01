"""Tests for `tools/recurrence.py` — DRY-into-seed candidate detector."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.recurrence import (
    scan_recurrence,
    scan_cross_product_helpers,
    scan_service_line_recurrence,
    scan_block_patterns,
    scan_within_product_helpers,
    scan_pydantic_model_shapes,
    scan_test_fixture_recurrence,
    scan_migration_patterns,
)


class TestScanRecurrence:
    def _mk_repo_with_main_files(self, products: dict[str, str]) -> Path:
        """Create temp repo with `products/<slug>/backend/app/main.py` files."""
        tmp = Path(tempfile.mkdtemp(prefix="recurrence_test_"))
        for slug, content in products.items():
            d = tmp / "products" / slug / "backend" / "app"
            d.mkdir(parents=True)
            (d / "main.py").write_text(content)
        return tmp

    def test_two_instances_warning_severity(self):
        repo = self._mk_repo_with_main_files({
            "p1": "from app.services import shared_thing  # noqa: F401\nrun_app()\n",
            "p2": "from app.services import shared_thing  # noqa: F401\nrun_app()\n",
        })
        result = scan_recurrence(repo, min_count=2)
        # The shared import line appears in 2 main.py files → warning.
        findings = result["findings"]
        line_texts = [f["line_text"] for f in findings]
        assert any("shared_thing" in t for t in line_texts)
        for f in findings:
            if "shared_thing" in f["line_text"]:
                assert f["severity"] == "warning"
                assert f["count"] == 2

    def test_three_plus_instances_high_severity(self):
        repo = self._mk_repo_with_main_files({
            "p1": "from app.services import recurrent_thing  # noqa: F401\n" + "x = 1\n" * 10,
            "p2": "from app.services import recurrent_thing  # noqa: F401\n" + "y = 2\n" * 10,
            "p3": "from app.services import recurrent_thing  # noqa: F401\n" + "z = 3\n" * 10,
        })
        result = scan_recurrence(repo)
        target = next(
            (f for f in result["findings"] if "recurrent_thing" in f["line_text"]),
            None,
        )
        assert target is not None, f"Findings: {[f['line_text'] for f in result['findings']]}"
        assert target["severity"] == "high"
        assert target["count"] == 3

    def test_seed_imports_ignored(self):
        # Lines starting with `from noctusai_seed` are inheritance, not replication.
        # Note: padding lines also need to be unique-per-file or they'd recur.
        repo = self._mk_repo_with_main_files({
            "p1": "from noctusai_seed import create_product_app\nx_p1 = create_product_app()\n",
            "p2": "from noctusai_seed import create_product_app\ny_p2 = create_product_app()\n",
            "p3": "from noctusai_seed import create_product_app\nz_p3 = create_product_app()\n",
        })
        result = scan_recurrence(repo)
        # No findings — the seed import is allowlisted.
        assert all(
            "noctusai_seed" not in f["line_text"]
            for f in result["findings"]
        )

    def test_short_lines_ignored(self):
        # Single instance under min_line_length should not register.
        repo = self._mk_repo_with_main_files({
            "p1": "import os\nimport sys\n",
            "p2": "import os\nimport sys\n",
        })
        result = scan_recurrence(repo, min_line_length=25)
        # `import os` is under 25 chars → ignored.
        assert all(
            f["line_text"] != "import os"
            for f in result["findings"]
        )

    def test_below_min_count_not_reported(self):
        repo = self._mk_repo_with_main_files({
            "p1": "from app.services import only_in_one_place_xyz  # noqa: F401\n",
        })
        result = scan_recurrence(repo, min_count=2)
        # Only 1 occurrence → not reported.
        assert all(
            "only_in_one_place_xyz" not in f["line_text"]
            for f in result["findings"]
        )

    def test_classifies_main_py_imports(self):
        repo = self._mk_repo_with_main_files({
            "p1": "from app.boilerplate import register_thing  # mark\n" * 1,
            "p2": "from app.boilerplate import register_thing  # mark\n" * 1,
        })
        result = scan_recurrence(repo, min_count=2)
        target = next(
            (f for f in result["findings"] if "register_thing" in f["line_text"]),
            None,
        )
        assert target is not None
        assert target["classification"] == "main.py-import"
        assert "create_product_app" in target["suggestion"]


class TestScanCrossProductHelpers:
    def _mk_repo(self, products: dict[str, dict[str, str]]) -> Path:
        """Create temp repo from `{slug: {relative_path: content}}`.

        Each file is placed at `products/<slug>/<relative_path>`.
        """
        tmp = Path(tempfile.mkdtemp(prefix="helpers_test_"))
        for slug, files in products.items():
            for rel, content in files.items():
                full = tmp / "products" / slug / rel
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content)
        return tmp

    def test_helper_recurring_in_two_products_warning(self):
        repo = self._mk_repo({
            "p1": {"backend/app/services/svc.py": "def _safe_float(x):\n    return float(x)\n"},
            "p2": {"backend/app/services/svc.py": "def _safe_float(s, default=0.0):\n    return float(s)\n"},
        })
        r = scan_cross_product_helpers(repo, min_count=2)
        target = next((f for f in r["findings"] if f["helper_name"] == "_safe_float"), None)
        assert target is not None
        assert target["product_count"] == 2
        assert target["severity"] == "warning"
        assert "parse/format helper" in target["suggestion"]
        assert "noctusai_lib.parsing" in target["suggestion"]

    def test_helper_recurring_in_three_products_high(self):
        repo = self._mk_repo({
            "p1": {"backend/app/services/x.py": "def _format_money(v):\n    return f'{v:.2f}'\n"},
            "p2": {"backend/app/services/y.py": "def _format_money(value):\n    return f'R$ {value}'\n"},
            "p3": {"backend/app/services/z.py": "def _format_money(amount):\n    return str(amount)\n"},
        })
        r = scan_cross_product_helpers(repo)
        target = next((f for f in r["findings"] if f["helper_name"] == "_format_money"), None)
        assert target is not None
        assert target["product_count"] == 3
        assert target["severity"] == "high"

    def test_router_handler_names_blacklisted(self):
        # `def list(...)` is a generic router handler — every product has one;
        # not absorption-shaped. Detector must NOT flag.
        repo = self._mk_repo({
            "p1": {"backend/app/routers/r.py": "def list(filter: str):\n    return []\n"},
            "p2": {"backend/app/routers/r.py": "def list(q: str):\n    return []\n"},
            "p3": {"backend/app/routers/r.py": "def list():\n    return []\n"},
        })
        r = scan_cross_product_helpers(repo)
        names = [f["helper_name"] for f in r["findings"]]
        assert "list" not in names

    def test_short_underscore_helper_filtered(self):
        # `_get` is too generic — bare 3 chars after underscore.
        repo = self._mk_repo({
            "p1": {"backend/app/services/a.py": "def _get():\n    pass\n"},
            "p2": {"backend/app/services/b.py": "def _get():\n    pass\n"},
        })
        r = scan_cross_product_helpers(repo)
        names = [f["helper_name"] for f in r["findings"]]
        assert "_get" not in names

    def test_one_product_not_flagged(self):
        repo = self._mk_repo({
            "p1": {"backend/app/services/svc.py": "def _only_here_unique_xyz():\n    pass\n"},
        })
        r = scan_cross_product_helpers(repo)
        names = [f["helper_name"] for f in r["findings"]]
        assert "_only_here_unique_xyz" not in names

    def test_frontend_hook_names_caught(self):
        # `useMetas` defined in 3 product hooks/ folders → high severity.
        repo = self._mk_repo({
            "p1": {"frontend/src/hooks/useMetas.ts": "export function useMetas() {\n  return [];\n}\n"},
            "p2": {"frontend/src/hooks/useMetas.ts": "export const useMetas = () => {\n  return [];\n}\n"},
            "p3": {"frontend/src/hooks/useMetas.ts": "export function useMetas(filter: string) {\n  return [];\n}\n"},
        })
        r = scan_cross_product_helpers(repo)
        target = next((f for f in r["findings"] if f["helper_name"] == "useMetas"), None)
        assert target is not None
        assert target["product_count"] == 3
        assert target["severity"] == "high"
        assert "frontend hook" in target["suggestion"].lower()

    def test_dataclass_class_recurrence(self):
        # `_PipelineHooks` defined in 2 products → flag for absorption.
        repo = self._mk_repo({
            "p1": {"backend/app/services/svc.py": "@dataclass\nclass _PipelineHooks:\n    transcribe: Callable\n"},
            "p2": {"backend/app/services/svc.py": "@dataclass\nclass _PipelineHooks:\n    summarize: Callable\n"},
        })
        r = scan_cross_product_helpers(repo)
        target = next((f for f in r["findings"] if f["helper_name"] == "_PipelineHooks"), None)
        assert target is not None
        assert target["product_count"] == 2
        assert "PipelineHooks-shape" in target["suggestion"] or "Hooks" in target["suggestion"]

    def test_same_product_multiple_files_counted_once(self):
        # If a product defines `_safe_float` in 3 files, count = 1 product.
        repo = self._mk_repo({
            "p1": {
                "backend/app/services/a.py": "def _safe_float(x):\n    return float(x)\n",
                "backend/app/services/b.py": "def _safe_float(x):\n    return float(x)\n",
                "backend/app/services/c.py": "def _safe_float(x):\n    return float(x)\n",
            },
            "p2": {"backend/app/services/x.py": "def _safe_float(x):\n    return float(x)\n"},
        })
        r = scan_cross_product_helpers(repo)
        target = next((f for f in r["findings"] if f["helper_name"] == "_safe_float"), None)
        assert target is not None
        assert target["product_count"] == 2  # not 4
        assert target["severity"] == "warning"


class TestScanServiceLineRecurrence:
    def _mk_repo(self, products: dict[str, dict[str, str]]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="service_line_test_"))
        for slug, files in products.items():
            for rel, content in files.items():
                full = tmp / "products" / slug / rel
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content)
        return tmp

    def test_iso_date_parse_pattern_caught(self):
        # The 22-site ISO-date pattern from the manual sweep — verbatim line in 3+ products.
        # Use a slightly longer realistic shape to clear the 60-char threshold.
        line = '    parsed_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))'
        repo = self._mk_repo({
            "p1": {"backend/app/services/svc.py": f"def f(timestamp_str):\n{line}\n    return parsed_dt\n"},
            "p2": {"backend/app/services/svc.py": f"def g(timestamp_str):\n{line}\n    return parsed_dt\n"},
            "p3": {"backend/app/services/svc.py": f"def h(timestamp_str):\n{line}\n    return parsed_dt\n"},
        })
        r = scan_service_line_recurrence(repo)
        target = next(
            (f for f in r["findings"] if "fromisoformat" in f["line_text"]),
            None,
        )
        assert target is not None, f"Got findings: {[f['line_text'] for f in r['findings']]}"
        assert target["product_count"] == 3
        assert target["severity"] == "high"
        assert "noctusai_lib.dates" in target["suggestion"]

    def test_imports_skipped(self):
        # `from noctusai_lib import x` recurs in every product — must NOT flag.
        repo = self._mk_repo({
            "p1": {"backend/app/services/x.py": "from noctusai_lib.audit import safely_log_action  # not absorption shape\ndef f(): pass\n"},
            "p2": {"backend/app/services/x.py": "from noctusai_lib.audit import safely_log_action  # not absorption shape\ndef g(): pass\n"},
            "p3": {"backend/app/services/x.py": "from noctusai_lib.audit import safely_log_action  # not absorption shape\ndef h(): pass\n"},
        })
        r = scan_service_line_recurrence(repo)
        for f in r["findings"]:
            assert "from noctusai_lib" not in f["line_text"]

    def test_short_lines_skipped(self):
        # `result.execute()` is too short to be meaningful absorption-shaped.
        repo = self._mk_repo({
            "p1": {"backend/app/services/x.py": "def f(q):\n    return q.execute()\n"},
            "p2": {"backend/app/services/x.py": "def g(q):\n    return q.execute()\n"},
            "p3": {"backend/app/services/x.py": "def h(q):\n    return q.execute()\n"},
        })
        r = scan_service_line_recurrence(repo, min_line_length=60)
        for f in r["findings"]:
            assert "return q.execute()" not in f["line_text"]

    def test_function_call_required(self):
        # Pure assignments (no `(`) are skipped even if long.
        constant = '    LONG_CONSTANT_VALUE_THAT_RECURS = "this is a sufficiently long constant"'
        repo = self._mk_repo({
            "p1": {"backend/app/services/x.py": f"def f():\n{constant}\n"},
            "p2": {"backend/app/services/x.py": f"def g():\n{constant}\n"},
        })
        r = scan_service_line_recurrence(repo)
        for f in r["findings"]:
            assert "LONG_CONSTANT_VALUE_THAT_RECURS" not in f["line_text"]

    def test_within_product_recurrence_not_flagged(self):
        # Same line 3 times in 1 product → product_count=1 → not flagged
        # (the tool focuses on cross-product DRY).
        line = '    raise HTTPException(status_code=400, detail="Bad request data here")'
        repo = self._mk_repo({
            "p1": {
                "backend/app/services/a.py": f"def f():\n{line}\n",
                "backend/app/services/b.py": f"def g():\n{line}\n",
                "backend/app/services/c.py": f"def h():\n{line}\n",
            },
        })
        r = scan_service_line_recurrence(repo)
        for f in r["findings"]:
            assert "Bad request data here" not in f["line_text"]


class TestScanBlockPatterns:
    def _mk_repo(self, products: dict[str, dict[str, str]]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="block_test_"))
        for slug, files in products.items():
            for rel, content in files.items():
                full = tmp / "products" / slug / rel
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content)
        return tmp

    def test_audit_log_pattern_detected(self):
        # Three try/except blocks calling `audit_service.log` with
        # `logger.warning` in the handler — same SHAPE, different identifiers
        # (different user_ids, different action strings).
        block_template = (
            "async def handler_{idx}(user_id):\n"
            "    try:\n"
            "        from app.services import audit_service\n"
            "        await audit_service.log(user_id=user_id, action='action_{idx}')\n"
            "    except Exception as exc:\n"
            "        logger.warning('audit log failed for user=%s', user_id)\n\n"
        )
        content = "import logging\nlogger = logging.getLogger(__name__)\n"
        for i in range(3):
            content += block_template.format(idx=i)

        repo = self._mk_repo({
            "p1": {"backend/app/services/svc.py": content},
        })
        r = scan_block_patterns(repo, min_count=2)
        target = next(
            (f for f in r["findings"] if "audit_service.log" in f["body_targets"]),
            None,
        )
        assert target is not None, f"Got: {[f['body_targets'] for f in r['findings']]}"
        assert target["occurrence_count"] == 3
        assert target["severity"] == "high"
        assert "safely_log_action" in target["suggestion"]

    def test_different_shapes_not_grouped(self):
        # Block A calls audit_service.log; Block B calls webhook_delivery.dispatch.
        # Different signatures → must NOT collapse.
        a = (
            "async def f():\n"
            "    try:\n"
            "        from app.services import audit_service\n"
            "        await audit_service.log()\n"
            "    except Exception as exc:\n"
            "        logger.warning('a')\n"
        )
        b = (
            "async def g():\n"
            "    try:\n"
            "        from app.services import webhook_delivery\n"
            "        await webhook_delivery.dispatch()\n"
            "    except Exception as exc:\n"
            "        logger.warning('b')\n"
        )
        repo = self._mk_repo({
            "p1": {"backend/app/services/x.py": "import logging\nlogger=logging.getLogger(__name__)\n" + a + b},
        })
        r = scan_block_patterns(repo, min_count=2)
        # Each block is unique → no recurrence.
        assert all(
            f["occurrence_count"] == 1
            for f in r["findings"]
        ), f"Unexpected recurrence: {r['findings']}"

    def test_cross_product_only_filter(self):
        # Block in 1 product × 3 instances should NOT flag when
        # cross_product_only=True.
        block = (
            "async def f_{idx}():\n"
            "    try:\n"
            "        await foo.bar()\n"
            "    except Exception as exc:\n"
            "        logger.warning('x')\n"
        )
        content = "\n".join(block.format(idx=i) for i in range(3))
        repo = self._mk_repo({
            "p1": {"backend/app/services/svc.py": content},
        })
        r_default = scan_block_patterns(repo, min_count=2, cross_product_only=False)
        r_xprod = scan_block_patterns(repo, min_count=2, cross_product_only=True)
        # Default: flagged (3 occurrences in 1 product).
        assert any(f["occurrence_count"] == 3 for f in r_default["findings"])
        # Cross-product only: filtered out.
        assert r_xprod["stats"]["total_findings"] == 0


class TestScanWithinProductHelpers:
    def _mk_repo(self, products: dict[str, dict[str, str]]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="within_test_"))
        for slug, files in products.items():
            for rel, content in files.items():
                full = tmp / "products" / slug / rel
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content)
        return tmp

    def test_helper_in_3_files_within_one_product(self):
        # `_safe_float` defined in 3 files of 1 product → flag.
        repo = self._mk_repo({
            "p1": {
                "backend/app/services/a.py": "def _safe_float(x):\n    return float(x)\n",
                "backend/app/services/b.py": "def _safe_float(x):\n    return float(x)\n",
                "backend/app/services/c.py": "def _safe_float(x):\n    return float(x)\n",
            },
        })
        r = scan_within_product_helpers(repo, min_count=3)
        target = next(
            (f for f in r["findings"] if f["helper_name"] == "_safe_float" and f["product"] == "p1"),
            None,
        )
        assert target is not None
        assert target["file_count"] == 3
        assert "p1/backend/app/utils.py" in target["suggestion"]

    def test_below_min_count_not_flagged(self):
        # 2 files within 1 product, default min_count=3 → not flagged.
        repo = self._mk_repo({
            "p1": {
                "backend/app/services/a.py": "def _helper_x(x): return x\n",
                "backend/app/services/b.py": "def _helper_x(x): return x\n",
            },
        })
        r = scan_within_product_helpers(repo, min_count=3)
        names = [f["helper_name"] for f in r["findings"]]
        assert "_helper_x" not in names

    def test_blacklisted_handler_names_filtered(self):
        # `criar` defined in 5 router files of 1 product is just per-resource
        # CRUD handler naming — must NOT flag.
        repo = self._mk_repo({
            "p1": {
                f"backend/app/routers/r{i}.py": f"async def criar():\n    pass\n"
                for i in range(5)
            },
        })
        r = scan_within_product_helpers(repo, min_count=3)
        names = [f["helper_name"] for f in r["findings"]]
        assert "criar" not in names


class TestScanPydanticModelShapes:
    def _mk_repo(self, products: dict[str, dict[str, str]]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="pyd_test_"))
        for slug, files in products.items():
            for rel, content in files.items():
                full = tmp / "products" / slug / rel
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content)
        return tmp

    def test_identical_field_set_in_two_products_flagged(self):
        model = (
            "from pydantic import BaseModel\n"
            "class LoginRequest(BaseModel):\n"
            "    email: str\n"
            "    password: str\n"
        )
        repo = self._mk_repo({
            "p1": {"backend/app/routers/auth.py": model},
            "p2": {"backend/app/routers/auth.py": model.replace("LoginRequest", "LoginInput")},
        })
        r = scan_pydantic_model_shapes(repo, min_count=2)
        assert r["stats"]["total_findings"] >= 1
        target = r["findings"][0]
        assert target["product_count"] == 2
        assert target["field_count"] == 2
        # The field set is sorted by (name, type)
        assert ["email", "str"] in target["field_set"]
        assert ["password", "str"] in target["field_set"]

    def test_single_field_models_filtered(self):
        # A 1-field model is too generic to flag (every product has
        # `class TokenIn: token: str` shapes).
        model = (
            "from pydantic import BaseModel\n"
            "class TokenIn(BaseModel):\n"
            "    token: str\n"
        )
        repo = self._mk_repo({
            "p1": {"backend/app/routers/x.py": model},
            "p2": {"backend/app/routers/x.py": model},
        })
        r = scan_pydantic_model_shapes(repo, min_count=2, min_field_count=2)
        assert r["stats"]["total_findings"] == 0

    def test_different_field_sets_not_grouped(self):
        m1 = (
            "from pydantic import BaseModel\n"
            "class A(BaseModel):\n"
            "    foo: str\n"
            "    bar: int\n"
        )
        m2 = (
            "from pydantic import BaseModel\n"
            "class B(BaseModel):\n"
            "    qux: str\n"
            "    baz: int\n"
        )
        repo = self._mk_repo({
            "p1": {"backend/app/routers/x.py": m1},
            "p2": {"backend/app/routers/x.py": m2},
        })
        r = scan_pydantic_model_shapes(repo, min_count=2)
        # Different shapes → no recurrence.
        assert r["stats"]["total_findings"] == 0

    def test_non_basemodel_classes_ignored(self):
        # Plain class (no BaseModel base) must not be flagged.
        plain = (
            "class A:\n"
            "    foo: str\n"
            "    bar: int\n"
        )
        repo = self._mk_repo({
            "p1": {"backend/app/services/x.py": plain},
            "p2": {"backend/app/services/x.py": plain.replace("class A:", "class B:")},
        })
        r = scan_pydantic_model_shapes(repo, min_count=2)
        assert r["stats"]["total_findings"] == 0


class TestScanTestFixtureRecurrence:
    def _mk_repo(self, products: dict[str, dict[str, str]]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="testfx_test_"))
        for slug, files in products.items():
            for rel, content in files.items():
                full = tmp / "products" / slug / rel
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content)
        return tmp

    def test_pytest_configure_recurrence_caught(self):
        # `pytest_configure` defined in 3 products' conftests → should flag.
        body = "def pytest_configure(config):\n    config.addinivalue_line('markers', 'realdb')\n"
        repo = self._mk_repo({
            "p1": {"backend/tests/conftest.py": body},
            "p2": {"backend/tests/conftest.py": body},
            "p3": {"backend/tests/conftest.py": body},
        })
        r = scan_test_fixture_recurrence(repo)
        target = next((f for f in r["findings"] if f["helper_name"] == "pytest_configure"), None)
        assert target is not None
        assert target["product_count"] == 3
        assert target["severity"] == "high"
        assert "noctusai_lib.testing" in target["suggestion"]

    def test_per_product_sample_constants_filtered(self):
        # `SAMPLE_APPOINTMENT` in conftest is per-product domain literal — not flagged
        # even if it appears identically in 2 products (which it won't in practice).
        body = "SAMPLE_APPOINTMENT = {'id': 'a-001', 'patient_id': 'p1'}\n"
        repo = self._mk_repo({
            "p1": {"backend/tests/conftest.py": body},
            "p2": {"backend/tests/conftest.py": body},
        })
        r = scan_test_fixture_recurrence(repo)
        names = [f["helper_name"] for f in r["findings"]]
        assert "SAMPLE_APPOINTMENT" not in names

    def test_test_methods_filtered(self):
        # `test_*` methods are per-product assertions — not absorption-shaped.
        body = "class T:\n    def test_login(self): pass\n    def test_logout(self): pass\n"
        repo = self._mk_repo({
            "p1": {"backend/tests/services/test_auth.py": body},
            "p2": {"backend/tests/services/test_auth.py": body},
        })
        r = scan_test_fixture_recurrence(repo)
        names = [f["helper_name"] for f in r["findings"]]
        assert "test_login" not in names
        assert "test_logout" not in names


class TestScanMigrationPatterns:
    def _mk_repo(self, products: dict[str, dict[str, str]]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="mig_test_"))
        for slug, files in products.items():
            for rel, content in files.items():
                full = tmp / "products" / slug / rel
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content)
        return tmp

    def test_rls_subquery_pattern_caught(self):
        rls_sql = (
            "CREATE POLICY clientes_select ON clientes FOR SELECT\n"
            "USING (auth.uid() IN (SELECT user_id FROM team_members));\n"
        )
        repo = self._mk_repo({
            "p1": {"backend/migrations/001_init.sql": rls_sql},
            "p2": {"backend/migrations/001_init.sql": rls_sql},
            "p3": {"backend/migrations/001_init.sql": rls_sql},
        })
        r = scan_migration_patterns(repo)
        target = next((f for f in r["findings"] if f["pattern_name"] == "rls_subquery_auth_uid"), None)
        assert target is not None
        assert target["product_count"] == 3
        assert target["severity"] == "high"

    def test_search_path_pattern_counted(self):
        sql = "SET search_path = 'public';\n"
        repo = self._mk_repo({
            "p1": {"backend/migrations/001.sql": sql + sql},  # 2 occurrences
            "p2": {"backend/migrations/001.sql": sql},
        })
        r = scan_migration_patterns(repo)
        target = next((f for f in r["findings"] if f["pattern_name"] == "search_path_lock"), None)
        assert target is not None
        assert target["total_occurrences"] == 3
        assert target["occurrences_by_product"]["p1"] == 2
        assert target["occurrences_by_product"]["p2"] == 1

    def test_pattern_in_one_product_not_flagged(self):
        rls_sql = "CREATE POLICY x ON t FOR SELECT USING (auth.uid() IN (SELECT user_id FROM y));\n"
        repo = self._mk_repo({
            "p1": {"backend/migrations/001.sql": rls_sql},
        })
        r = scan_migration_patterns(repo)
        names = [f["pattern_name"] for f in r["findings"]]
        assert "rls_subquery_auth_uid" not in names
