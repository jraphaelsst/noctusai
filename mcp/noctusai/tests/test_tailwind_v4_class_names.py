"""Colocated regression test for `check_tailwind_v4_class_names` (meta-detector: every
keeper ships Test<CamelCase>)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_tailwind_v4_class_names,
    tailwind_v4_class_name_hits,
)


def _repo(tmp_path: Path, rel: str, src: str) -> Path:
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(src, encoding="utf-8")
    return f


class TestTailwindV4ClassNames:
    def test_clean_case_no_issues(self, tmp_path):
        assert check_tailwind_v4_class_names(paths=[], repo_root=tmp_path) == []

    def test_violation_flagged(self, tmp_path):
        f = _repo(tmp_path, "seed/lib/frontend/src/A.tsx",
                  'export const A = () => <div className="rounded shadow-sm focus-visible:outline-none" />;\n')
        issues = check_tailwind_v4_class_names(paths=[f], repo_root=tmp_path)
        assert [i["severity"] for i in issues] == ["high", "high"]
        assert issues[0]["file"] == "seed/lib/frontend/src/A.tsx:1"

    def test_v4_names_and_lookalikes_are_clean(self):
        src = ('const c = "shadow-xs shadow-sm-ish outline-hidden hover:shadow-md drop-shadow-sm";\n'
               'const d = cn("ring-2", isOpen && "shadow-lg");\n')
        assert tailwind_v4_class_name_hits(src) == []

    def test_variants_and_important_are_flagged(self):
        src = 'const c = `md:!shadow-sm ${x} hover:outline-none!`;\n'
        assert len(tailwind_v4_class_name_hits(src)) == 2

    def test_comments_and_escape_are_skipped(self):
        src = (" *   - `shadow-sm` for subtle elevation\n"
               "// outline-none is v3\n"
               'const c = "shadow-sm"; // noc-allow: tailwind-v3-class — third-party markup kept verbatim\n')
        assert tailwind_v4_class_name_hits(src) == []

    def test_lucide_brand_import_flagged_brand_icons_clean(self):
        bad = 'import {\n  Bot,\n  Instagram,\n} from "lucide-react";\n'
        good = 'import { Bot } from "lucide-react";\nimport { Instagram } from "@noctusai/lib/brand-icons";\n'
        hits = tailwind_v4_class_name_hits(bad)
        assert len(hits) == 1 and "brand-icons" in hits[0][1]
        assert tailwind_v4_class_name_hits(good) == []
