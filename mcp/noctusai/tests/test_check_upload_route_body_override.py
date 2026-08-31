"""`check_upload_route_body_override` — the STATIC BACKSTOP for the
`max_body_path_overrides` hand-maintained-list-drift class (sibling of
`check_dependabot_product_coverage` / `check_ci_test_matrix_coverage`).

WHY (2026-08-31). `MaxBodySizeMiddleware` caps every inbound request body at
1 MB by default — a webhook DoS guard. A route receiving a real browser
upload needs a bigger, PER-ROUTE cap declared in a product's
`max_body_path_overrides` map. That map is hand-maintained: only
`social-wiring` carried ANY entries, and even it was missing 3 of its own
upload routes (`/api/chat/upload-file`, `/api/leads/import/preview`,
`/api/leads/import/commit`); four other products
(`erp-imobiliario`/`igig`/`adconnect`/`therapy-platform`) had upload routes
and ZERO entries. A forgotten entry doesn't fail a fixture-sized test — it
413s only on a realistically-sized upload, in production.

The PRIMARY, exhaustive mechanism is a runtime refusal:
`noctusai_seed.app.create_product_app` (via
`noctusai_seed.upload_route_overrides.enforce_upload_route_overrides`)
walks the live, fully-mounted route table after boot and refuses to start
if a gap exists — see `seed/framework/backend/tests/test_upload_route_overrides.py`
for that mechanism's own regression suite. THIS file pins the STATIC
commit-time backstop instead, so the tests below never boot a FastAPI app —
they write small synthetic `products/<slug>/backend/app/**` trees under
`tmp_path` and assert on `check_upload_route_body_override(tmp_path)`.

NOTE ON THE LIVE REPO: as of this commit the real tree is EXPECTED to be
red (13 known gaps across 5 products) until the sibling slice
`feat/upload-cap-fleet-ceilings` lands each product's real ceilings — this
file therefore has NO "the real repo is currently green" assertion (unlike
some sibling keeper tests); the historical-shape test below reproduces the
gap synthetically instead, so it stays meaningful whether or not the
sibling slice has merged yet.

→ KB § PATTERNS/backend/upload-route-body-override-derivation.md
"""
from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_upload_route_body_override  # noqa: E402


def _write(root: Path, rel_path: str, content: str) -> Path:
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dedent(content))
    return p


def _write_main(root: Path, slug: str, overrides_body: str = "") -> Path:
    """Minimal `app/main.py` — just enough for the AST walk to find a
    `create_product_app(..., max_body_path_overrides=...)` call. Passing
    `overrides_body=""` mirrors a product with NO overrides declared at
    all (the erp-imobiliario/igig/adconnect/therapy-platform shape).

    Built by joining already-column-0 lines (NOT a single indented
    triple-quoted f-string dedented afterwards) — `overrides_body` can
    itself be multi-line (an import + a dict literal), and
    `textwrap.dedent` only strips a prefix common to EVERY line, so one
    zero-indent line mixed into an otherwise-indented block defeats it
    silently (a genuine test-fixture bug caught by
    `test_keep_default_max_body_sentinel_counts_as_covered` initially
    failing for the wrong reason — a SyntaxError swallowed by the
    detector's own graceful-degrade, not a real detector miss)."""
    lines = ["from noctusai_seed import create_product_app", ""]
    if overrides_body:
        lines.append(overrides_body)
        lines.append("")
    lines.append("app = create_product_app(")
    lines.append('    name="Test",')
    lines.append('    schema="test",')
    lines.append("    settings=settings,")
    lines.append("    routers=[],")
    if overrides_body:
        lines.append("    max_body_path_overrides=_MAX_BODY_PATH_OVERRIDES,")
    lines.append(")")
    body = "\n".join(lines) + "\n"
    p = root / f"products/{slug}/backend/app/main.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


# ─────────────────────────────────────────────────────────────────────────
# Annotation-shape detection — one fixture per shape (mirrors the runtime
# detector's own per-shape coverage in
# seed/framework/backend/tests/test_upload_route_overrides.py, at the
# static-analysis layer this time).
# ─────────────────────────────────────────────────────────────────────────


class TestAnnotationShapeDetection:
    def test_bare_upload_file(self, tmp_path):
        _write_main(tmp_path, "p1")
        _write(
            tmp_path,
            "products/p1/backend/app/routers/docs.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/docs")

            @router.post("/upload")
            async def upload(file: UploadFile = File(...)):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1, issues
        assert "/api/docs/upload" in issues[0]["issue"]

    def test_list_upload_file_lowercase_generic(self, tmp_path):
        _write_main(tmp_path, "p1")
        _write(
            tmp_path,
            "products/p1/backend/app/routers/docs.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/docs")

            @router.post("/upload-multiple")
            async def upload(files: list[UploadFile] = File(...)):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1, issues
        assert "/api/docs/upload-multiple" in issues[0]["issue"]

    def test_list_upload_file_typing_generic(self, tmp_path):
        _write_main(tmp_path, "p1")
        _write(
            tmp_path,
            "products/p1/backend/app/routers/docs.py",
            """
            from typing import List
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/docs")

            @router.post("/upload-multiple")
            async def upload(files: List[UploadFile] = File(...)):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1, issues

    def test_upload_file_or_none_pep604(self, tmp_path):
        _write_main(tmp_path, "p1")
        _write(
            tmp_path,
            "products/p1/backend/app/routers/chat.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/chat")

            @router.post("/message")
            async def message(file: UploadFile | None = File(None)):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1, issues
        assert "/api/chat/message" in issues[0]["issue"]

    def test_optional_upload_file_typing_union(self, tmp_path):
        _write_main(tmp_path, "p1")
        _write(
            tmp_path,
            "products/p1/backend/app/routers/chat.py",
            """
            from typing import Optional
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/chat")

            @router.post("/message")
            async def message(file: Optional[UploadFile] = File(None)):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1, issues

    def test_annotated_upload_file(self, tmp_path):
        _write_main(tmp_path, "p1")
        _write(
            tmp_path,
            "products/p1/backend/app/routers/docs.py",
            """
            from typing import Annotated
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/docs")

            @router.post("/upload")
            async def upload(file: Annotated[UploadFile, File(...)]):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1, issues

    def test_non_upload_route_is_never_flagged(self, tmp_path):
        _write_main(tmp_path, "p1")
        _write(
            tmp_path,
            "products/p1/backend/app/routers/docs.py",
            """
            from fastapi import APIRouter
            router = APIRouter(prefix="/api/docs")

            @router.get("/list")
            async def list_docs(q: str = ""):
                return []
            """,
        )
        assert check_upload_route_body_override(tmp_path) == []


# ─────────────────────────────────────────────────────────────────────────
# Prefix resolution — constructor-time `prefix=`, the post-hoc
# `router.prefix = "..."` legacy pattern, and dynamic-segment -> `*`
# pattern-key conversion.
# ─────────────────────────────────────────────────────────────────────────


class TestPrefixResolution:
    def test_dynamic_segment_becomes_wildcard_in_the_pattern_key(self, tmp_path):
        _write_main(tmp_path, "p1")
        _write(
            tmp_path,
            "products/p1/backend/app/routers/clientes.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/clientes")

            @router.post("/{cliente_id}/documentos")
            async def upload(cliente_id: str, file: UploadFile = File(...)):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1, issues
        assert "/api/clientes/*/documentos" in issues[0]["issue"]

    def test_post_hoc_prefix_assignment_is_honored(self, tmp_path):
        # The adconnect legacy pattern: `router = APIRouter(tags=[...])`
        # with NO prefix kwarg, then `router.prefix = "/sellout"` assigned
        # elsewhere (in this case, main.py-style, but same file here for
        # a minimal fixture).
        _write_main(tmp_path, "p1")
        _write(
            tmp_path,
            "products/p1/backend/app/routers/sellout.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(tags=["sellout"])
            router.prefix = "/sellout"

            @router.post("/upload-nfe")
            async def upload(file: UploadFile = File(...)):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1, issues
        assert "/sellout/upload-nfe" in issues[0]["issue"]

    def test_non_router_file_is_ignored(self, tmp_path):
        # A file with no `APIRouter(...)` assignment at all — e.g. a
        # service module that happens to accept an UploadFile parameter
        # in a plain (non-route) function. Must not be scanned as if it
        # were a router.
        _write_main(tmp_path, "p1")
        _write(
            tmp_path,
            "products/p1/backend/app/services/uploads_service.py",
            """
            from fastapi import UploadFile

            async def store(file: UploadFile) -> str:
                return "ok"
            """,
        )
        assert check_upload_route_body_override(tmp_path) == []


# ─────────────────────────────────────────────────────────────────────────
# Coverage — pattern match, prefix match (incl. a deeper sibling route),
# and the KEEP_DEFAULT_MAX_BODY opt-out.
# ─────────────────────────────────────────────────────────────────────────


class TestCoverage:
    def test_unparseable_main_py_degrades_to_no_overrides_not_a_crash(self, tmp_path):
        # A malformed main.py (any SyntaxError) must not blow up the
        # detector — it degrades to "no overrides found" (every upload
        # route in this product is then reported, which is honest: an
        # override-map this keeper can't even parse is not "covered").
        p = tmp_path / "products/p1/backend/app/main.py"
        p.parent.mkdir(parents=True)
        p.write_text("this is not valid python (((")
        _write(
            tmp_path,
            "products/p1/backend/app/routers/docs.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/docs")

            @router.post("/upload")
            async def upload(file: UploadFile = File(...)):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1, issues

    def test_pattern_override_covers_the_matching_dynamic_route(self, tmp_path):
        _write_main(
            tmp_path,
            "p1",
            overrides_body='_MAX_BODY_PATH_OVERRIDES = {"/api/clientes/*/documentos": 30_000_000}',
        )
        _write(
            tmp_path,
            "products/p1/backend/app/routers/clientes.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/clientes")

            @router.post("/{cliente_id}/documentos")
            async def upload(cliente_id: str, file: UploadFile = File(...)):
                return {}
            """,
        )
        assert check_upload_route_body_override(tmp_path) == []

    def test_prefix_override_covers_a_deeper_sibling_route(self, tmp_path):
        # Mirrors the real social-wiring shape: "/api/videos/upload" (a
        # plain-prefix entry) also covers "/api/videos/upload/from-code"
        # via longest-prefix matching, not an exact key.
        _write_main(
            tmp_path,
            "p1",
            overrides_body='_MAX_BODY_PATH_OVERRIDES = {"/api/videos/upload": 500_000_000}',
        )
        _write(
            tmp_path,
            "products/p1/backend/app/routers/upload.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/videos/upload")

            @router.post("")
            async def base(file: UploadFile = File(...)):
                return {}

            @router.post("/from-code")
            async def from_code(file: UploadFile = File(...)):
                return {}
            """,
        )
        assert check_upload_route_body_override(tmp_path) == []

    def test_keep_default_max_body_sentinel_counts_as_covered(self, tmp_path):
        _write_main(
            tmp_path,
            "p1",
            overrides_body=(
                "from noctusai_lib.api.middleware import KEEP_DEFAULT_MAX_BODY\n"
                '_MAX_BODY_PATH_OVERRIDES = {"/api/avatar/upload": KEEP_DEFAULT_MAX_BODY}'
            ),
        )
        _write(
            tmp_path,
            "products/p1/backend/app/routers/avatar.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/avatar")

            @router.post("/upload")
            async def upload(file: UploadFile = File(...)):
                return {}
            """,
        )
        assert check_upload_route_body_override(tmp_path) == []

    def test_different_segment_count_under_same_prefix_is_not_covered(self, tmp_path):
        # A pattern override only covers its EXACT segment-shape — the
        # same discipline `MaxBodySizeMiddleware._pattern_matches`
        # enforces at runtime (a pattern must not accidentally widen).
        _write_main(
            tmp_path,
            "p1",
            overrides_body='_MAX_BODY_PATH_OVERRIDES = {"/api/clientes/*/documentos": 30_000_000}',
        )
        _write(
            tmp_path,
            "products/p1/backend/app/routers/clientes.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/clientes")

            @router.post("/{cliente_id}/financiamento/documentos")
            async def upload(cliente_id: str, file: UploadFile = File(...)):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1, issues
        assert "/api/clientes/*/financiamento/documentos" in issues[0]["issue"]

    def test_no_overrides_declared_at_all_flags_every_upload_route(self, tmp_path):
        # erp-imobiliario/igig/adconnect/therapy-platform's CURRENT shape:
        # no max_body_path_overrides kwarg in main.py whatsoever.
        _write_main(tmp_path, "p1")  # overrides_body="" -> no kwarg at all
        _write(
            tmp_path,
            "products/p1/backend/app/routers/docs.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/docs")

            @router.post("/upload")
            async def upload(file: UploadFile = File(...)):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1, issues


# ─────────────────────────────────────────────────────────────────────────
# Reproduces the historical-shape gap (synthetic — never against the real
# repo, which is expected red right now pending the sibling slice).
# ─────────────────────────────────────────────────────────────────────────


class TestReproducesTheHistoricalGapShape:
    def test_partial_coverage_flags_only_the_gap_across_products(self, tmp_path):
        # social-wiring-shaped: ONE covered route, ONE forgotten route.
        _write_main(
            tmp_path,
            "social-wiring",
            overrides_body=(
                '_MAX_BODY_PATH_OVERRIDES = {"/api/videos/upload": 500_000_000}'
            ),
        )
        _write(
            tmp_path,
            "products/social-wiring/backend/app/routers/chat_router.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/chat")

            @router.post("/upload-file")
            async def stage_chat_file(file: UploadFile = File(...)):
                return {}
            """,
        )
        _write(
            tmp_path,
            "products/social-wiring/backend/app/modules/youtube/routers/upload.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/videos/upload")

            @router.post("")
            async def upload_video(file: UploadFile = File(...)):
                return {}
            """,
        )
        # erp-imobiliario-shaped: NO overrides declared at all.
        _write_main(tmp_path, "erp-imobiliario")
        _write(
            tmp_path,
            "products/erp-imobiliario/backend/app/routers/storage.py",
            """
            from typing import List
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/storage")

            @router.post("/upload")
            async def upload_file(file: UploadFile = File(...)):
                return {}

            @router.post("/upload-multiple")
            async def upload_multiple_files(files: List[UploadFile] = File(...)):
                return {}
            """,
        )

        issues = check_upload_route_body_override(tmp_path)
        by_product: dict[str, int] = {}
        for i in issues:
            by_product[i["product"]] = by_product.get(i["product"], 0) + 1

        assert by_product == {"social-wiring": 1, "erp-imobiliario": 2}, issues
        assert all(i["severity"] == "high" for i in issues)


# ─────────────────────────────────────────────────────────────────────────
# `TestCheckUploadRouteBodyOverride` — named for `check_detector_has_
# regression_test`'s `Test<CamelCase>` heuristic; the mandated
# true-positive / false-positive pair.
# ─────────────────────────────────────────────────────────────────────────


class TestCheckUploadRouteBodyOverride:
    def test_true_positive_uncovered_upload_route_is_flagged(self, tmp_path):
        _write_main(tmp_path, "widgets")
        _write(
            tmp_path,
            "products/widgets/backend/app/routers/docs.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/docs")

            @router.post("/upload")
            async def upload(file: UploadFile = File(...)):
                return {}
            """,
        )
        issues = check_upload_route_body_override(tmp_path)
        assert len(issues) == 1
        assert issues[0]["product"] == "widgets"
        assert issues[0]["severity"] == "high"
        assert "max_body_path_overrides" in issues[0]["issue"]
        assert "KEEP_DEFAULT_MAX_BODY" in issues[0]["issue"]

    def test_false_positive_covered_upload_route_is_clean(self, tmp_path):
        _write_main(
            tmp_path,
            "widgets",
            overrides_body='_MAX_BODY_PATH_OVERRIDES = {"/api/docs/upload": 10_000_000}',
        )
        _write(
            tmp_path,
            "products/widgets/backend/app/routers/docs.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/docs")

            @router.post("/upload")
            async def upload(file: UploadFile = File(...)):
                return {}
            """,
        )
        assert check_upload_route_body_override(tmp_path) == []

    def test_no_products_dir_no_crash(self, tmp_path):
        assert check_upload_route_body_override(tmp_path) == []

    def test_test_and_migration_files_are_skipped(self, tmp_path):
        _write_main(tmp_path, "widgets")
        _write(
            tmp_path,
            "products/widgets/backend/app/tests/routers/test_docs.py",
            """
            from fastapi import APIRouter, File, UploadFile
            router = APIRouter(prefix="/api/docs")

            @router.post("/upload")
            async def upload(file: UploadFile = File(...)):
                return {}
            """,
        )
        assert check_upload_route_body_override(tmp_path) == []
