"""`check_model_dump_json_mode` — a raw `.model_dump()` must not reach a supabase write.

The orbity 2026-10-15 live 502 ("Object of type UUID is not JSON serializable"):
a request model dumped with the default mode="python" keeps UUID/datetime
objects, and supabase-py's stdlib json encoder refuses them.
→ KB § PATTERNS/backend/backend.md § Pydantic → supabase writes
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_model_dump_json_mode,
    model_dump_json_mode_report,
)

APP = "products/acme/backend/app"


def _repo(tmp_path: Path, files: dict[str, str], active=("acme",)) -> Path:
    scope = tmp_path / "deploy" / "fleet" / "active-scope.txt"
    scope.parent.mkdir(parents=True, exist_ok=True)
    scope.write_text("\n".join(active) + "\n")
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body))
    return tmp_path


def _lines(issues) -> list[int]:
    return sorted(i["line"] for i in issues)


class TestModelDumpJsonMode:
    """Positive shapes — each must be flagged at the sink line."""

    def test_direct_argument_to_insert(self, tmp_path):
        root = _repo(tmp_path, {f"{APP}/r.py": """\
            def create(sb, body):
                return sb.table("t").insert(body.model_dump()).execute()
            """})
        got = check_model_dump_json_mode(root)
        assert _lines(got) == [2]
        assert got[0]["product"] == "acme" and got[0]["severity"] == "high"

    def test_via_local_variable_to_update(self, tmp_path):
        root = _repo(tmp_path, {f"{APP}/r.py": """\
            def patch(sb, body, rid):
                data = body.model_dump(exclude_unset=True)
                data["updated_at"] = "now"
                return sb.table("t").update(data).eq("id", rid).execute()
            """})
        assert _lines(check_model_dump_json_mode(root)) == [4]

    def test_via_dict_merge_to_upsert(self, tmp_path):
        root = _repo(tmp_path, {f"{APP}/r.py": """\
            def put(sb, body, org):
                row = {**body.model_dump(), "org_id": org}
                sb.table("t").upsert(row).execute()
            """})
        assert _lines(check_model_dump_json_mode(root)) == [3]

    def test_via_service_create_call(self, tmp_path):
        root = _repo(tmp_path, {f"{APP}/r.py": """\
            async def create(svc, body, org):
                payload = body.model_dump()
                return await svc.create_campaign(org, payload)
            """})
        assert _lines(check_model_dump_json_mode(root)) == [3]

    def test_transitive_shapes(self, tmp_path):
        root = _repo(tmp_path, {f"{APP}/r.py": """\
            def a(sb, body):
                d = body.model_dump()
                e = dict(d)
                sb.table("t").insert(e).execute()

            def b(sb, items):
                sb.table("t").insert([i.model_dump() for i in items]).execute()

            def c(sb, body):
                row = {"org": 1}
                row.update(body.model_dump())
                sb.table("t").insert(row).execute()

            def d(repo, body):
                repo.criar({k: v for k, v in body.model_dump().items() if v is not None})

            def e(svc, body):
                svc.update(1, payload=body.model_dump(mode="python"))
            """})
        assert _lines(check_model_dump_json_mode(root)) == [4, 7, 12, 15, 18]


class TestModelDumpJsonModeNegatives:
    """Shapes that must NOT be flagged."""

    def test_mode_json_is_clean(self, tmp_path):
        root = _repo(tmp_path, {f"{APP}/r.py": """\
            def create(sb, svc, body):
                data = body.model_dump(mode="json", exclude_unset=True)
                sb.table("t").insert(data).execute()
                svc.create_x({**body.model_dump(mode="json"), "a": 1})
            """})
        assert check_model_dump_json_mode(root) == []

    def test_dump_for_response_or_log_is_clean(self, tmp_path):
        root = _repo(tmp_path, {f"{APP}/r.py": """\
            import logging
            def get(row, Out):
                out = Out(**row).model_dump()
                logging.info("row %s", out)
                return {"data": out}

            def merge(body):
                d = {}
                d.update(body.model_dump())
                return d
            """})
        assert check_model_dump_json_mode(root) == []

    def test_escape_comment_on_sink_or_dump_line(self, tmp_path):
        root = _repo(tmp_path, {f"{APP}/r.py": """\
            def a(sb, body):
                sb.table("t").insert(body.model_dump()).execute()  # noc-allow: model-dump-json — str-only model

            def b(sb, body):
                d = body.model_dump()  # noc-allow: model-dump-json — fields are all str
                sb.table("t").insert(d).execute()

            def c(sb, body):
                sb.table("t").insert(body.model_dump()).execute()  # noc-allow: model-dump-json
            """})
        # c: a bare marker without a reason does not count
        assert _lines(check_model_dump_json_mode(root)) == [9]

    def test_taint_is_function_local(self, tmp_path):
        root = _repo(tmp_path, {f"{APP}/r.py": """\
            def a(body):
                data = body.model_dump()
                return data

            def b(sb, data):
                sb.table("t").insert(data).execute()
            """})
        assert check_model_dump_json_mode(root) == []


class TestModelDumpJsonModeScope:
    BAD = """\
        def create(sb, body):
            sb.table("t").insert(body.model_dump()).execute()
        """

    def test_asleep_product_is_skipped(self, tmp_path):
        root = _repo(tmp_path, {
            f"{APP}/r.py": self.BAD,
            "products/sleepy/backend/app/r.py": self.BAD,
        })
        assert {i["product"] for i in check_model_dump_json_mode(root)} == {"acme"}

    def test_only_backend_app_is_scanned(self, tmp_path):
        root = _repo(tmp_path, {
            "products/acme/backend/tests/test_r.py": self.BAD,
            "products/acme/backend/scripts/r.py": self.BAD,
            "seed/lib/backend/x/r.py": self.BAD,
        })
        assert check_model_dump_json_mode(root) == []

    def test_paths_mode_judges_only_given_files(self, tmp_path):
        root = _repo(tmp_path, {
            f"{APP}/touched.py": self.BAD,
            f"{APP}/untouched.py": self.BAD,
            "products/sleepy/backend/app/r.py": self.BAD,
        })
        got = check_model_dump_json_mode(
            root, paths=[f"{APP}/touched.py", "products/sleepy/backend/app/r.py", "README.md"])
        assert [i["file"] for i in got] == [f"{APP}/touched.py"]
        assert check_model_dump_json_mode(root, paths=[]) == []

    def test_report_counts_per_product(self, tmp_path):
        root = _repo(tmp_path, {
            f"{APP}/a.py": self.BAD,
            f"{APP}/b.py": self.BAD,
            "products/beta/backend/app/r.py": self.BAD,
        }, active=("acme", "beta"))
        rep = model_dump_json_mode_report(root)
        assert rep["status"] == "violation" and rep["total"] == 3
        assert rep["by_product"] == {"acme": 2, "beta": 1}
