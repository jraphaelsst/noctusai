"""`check_motion_import_boundary` — Motion is imported ONLY via `@noctusai/lib/marketing`.

Red fixtures: every import shape of `motion` / `framer-motion` in a product, the template, or the
seed lib outside `marketing/`. Green fixtures: the `@noctusai/lib/marketing` seam, look-alike
packages, the seam dir itself, and the reasoned escape marker.

→ KB § PATTERNS/frontend/marketing-organs-and-motion.md
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    REPO_ROOT,
    _MOTION_SCRIPT_REL,
    check_motion_import_boundary,
)

_SCRIPT = REPO_ROOT.joinpath(*_MOTION_SCRIPT_REL)
_TOOLING = (
    shutil.which("node") is not None
    and _SCRIPT.exists()
    and (_SCRIPT.parent / "node_modules" / "ts-morph").exists()
)
pytestmark = pytest.mark.skipif(
    not _TOOLING, reason="node / ts-morph unavailable — run `cd mcp/noctusai/node && npm ci`"
)

PRODUCT = "products/demo/frontend/src/Hero.tsx"
TEMPLATE = "templates/product-seed/frontend/src/Hero.tsx"
SEED_LIB = "seed/lib/frontend/src/organs/Fancy.tsx"
SEED_MARKETING = "seed/lib/frontend/src/marketing/MotionProvider.tsx"


def _run(tmp: Path, files: dict[str, str]) -> list[dict]:
    for rel, text in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return check_motion_import_boundary(repo_root=tmp)


class TestCheckMotionImportBoundary:
    @pytest.mark.parametrize("spec", [
        "motion", "motion/react", "motion/react-client", "motion/react-m", "motion/dom",
        "framer-motion", "framer-motion/dom",
    ])
    def test_banned_specifiers_flagged_in_product(self, tmp_path, spec):
        issues = _run(tmp_path, {PRODUCT: f'import {{ motion }} from "{spec}";\nexport const X = 1;\n'})
        assert len(issues) == 1
        assert issues[0]["file"] == PRODUCT and issues[0]["line"] == 1 and issues[0]["severity"] == "high"
        assert f"`{spec}`" in issues[0]["issue"]

    @pytest.mark.parametrize("src", [
        'import "motion/react";\n',
        'export { motion } from "motion/react";\n',
        'export * from "framer-motion";\n',
        'const m = () => import("motion/react");\n',
        'const m = require("framer-motion");\n',
        'import type { Variants } from "motion/react";\n',
    ])
    def test_every_import_shape_flagged(self, tmp_path, src):
        assert len(_run(tmp_path, {PRODUCT: src})) == 1

    def test_template_and_seed_lib_flagged(self, tmp_path):
        issues = _run(tmp_path, {
            TEMPLATE: 'import { m } from "motion/react";\n',
            SEED_LIB: 'import { m } from "motion/react";\n',
        })
        assert sorted(i["file"] for i in issues) == sorted([TEMPLATE, SEED_LIB])

    # ─── green ───
    def test_marketing_seam_import_allowed(self, tmp_path):
        src = 'import { Hero, MotionProvider } from "@noctusai/lib/marketing";\n'
        assert _run(tmp_path, {PRODUCT: src}) == []

    def test_lookalike_packages_allowed(self, tmp_path):
        src = 'import a from "motion-canvas";\nimport b from "@scope/motion";\nimport c from "react-motion";\n'
        assert _run(tmp_path, {PRODUCT: src}) == []

    def test_seed_marketing_dir_is_the_seam(self, tmp_path):
        assert _run(tmp_path, {SEED_MARKETING: 'import { LazyMotion } from "motion/react";\n'}) == []

    def test_text_in_comment_or_string_not_flagged(self, tmp_path):
        src = '// import x from "motion/react"\nexport const s = \'import y from "framer-motion"\';\n'
        assert _run(tmp_path, {PRODUCT: src}) == []

    def test_escape_marker_with_reason_allows(self, tmp_path):
        src = '// noc-allow: motion-import — one-off canvas demo, reviewed\nimport { m } from "motion/react";\n'
        assert _run(tmp_path, {PRODUCT: src}) == []

    def test_escape_marker_without_reason_does_not_allow(self, tmp_path):
        src = '// noc-allow: motion-import\nimport { m } from "motion/react";\n'
        assert len(_run(tmp_path, {PRODUCT: src})) == 1

    def test_tree_without_marketing_dir_or_sources_is_clean(self, tmp_path):
        assert check_motion_import_boundary(repo_root=tmp_path) == []

    def test_unparsable_file_is_not_a_silent_pass_or_crash(self, tmp_path):
        # TypeScript parses leniently; the contract is: never raises, never claims motion was found.
        issues = _run(tmp_path, {PRODUCT: "export const = = ;\n"})
        assert all("motion" not in i["issue"].lower() or "could not" in i["issue"] for i in issues)


def test_live_tree_is_clean():
    """Named for `check_motion_import_boundary` so `check_detector_has_regression_test` finds it."""
    issues = check_motion_import_boundary()
    assert issues == [], issues
