"""Regression tests for the Stage-4 codification pair shipped 2026-05-17.

Two warn-/error-only keeper detectors promoted to Stage 4, combined in one
change (they share the detector-module / registry surface):

  - `check_doc_symbology_drift`          (project symbol-first-stage-4-
    codification; N=3 drift signal — symbol-first authoring methodology)
  - `check_dockerfile_vite_supabase_args`(containerization single-container;
    boot-critical VITE_SUPABASE_* build-arg contract)

Each gets a focused `Test<CamelCase>` class with positive-fires +
negative-doesn't-fire + edge-case tests. File-system-scoped (`tmp_path`),
no monkey-patching of our own code — the seed test pattern.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_dockerfile_vite_supabase_args,
    check_doc_symbology_drift,
)


# ---------------------------------------------------------------------------
# check_doc_symbology_drift
# ---------------------------------------------------------------------------

# A minimal but format-faithful doc-symbology.md §1 — only the rows the
# detector parses (first cell of `| <sym> | … |`). Mirrors the live
# glossary's table shape exactly.
_GLOSSARY = """# Doc Symbology

## 1. Core symbol inventory

### Logic & set theory
| Symbol | Meaning | Example |
|---|---|---|
| `∧` | AND | x |
| `∨` | OR | x |
| `¬` | NOT | x |
| `⇒` | implies | x |
| `↔` | bidirectional | x |

### Counts & comparisons
| Symbol | Meaning | Example |
|---|---|---|
| `N≥3`, `N=2`, `N=1` | recurrence count | x |
| `≥`, `≤` | gte / lte | x |
| `Δ` | delta | x |
| `Σ` | sum | x |
| `±` | plus-or-minus | x |

### Status
| Symbol | Meaning |
|---|---|
| `✅` | done |
| `⏳` | in-progress |
| `🟢` `🟡` `🔴` | severity |

### Code & pipeline
| Symbol | Meaning | Example |
|---|---|---|
| `→` | routes-to | x |
| `s1`/`s2`/`s3`/`s4` | stages | x |
"""


class TestCheckDocSymbologyDrift:
    """Dense docs must obey the doc-symbology glossary contract: no
    out-of-glossary symbology glyphs in symbol-eligible docs (the locked
    §3/§5 core; the unlocked Q4 `→`/`⇒` strict-interchange is NOT done).
    """

    def _mk_glossary(self, tmp_path: Path, text: str = _GLOSSARY) -> None:
        # 2026-05-26 PATTERNS reorg moved the glossary into common/.
        gp = tmp_path / "KNOWLEDGE-BASE" / "CONTEXT" / "PATTERNS" / "common"
        gp.mkdir(parents=True, exist_ok=True)
        (gp / "doc-symbology.md").write_text(text)

    def _mk_kb_pattern(self, tmp_path: Path, body: str, *, name: str = "x.md") -> None:
        # Place under common/ — matches the post-reorg glob
        # `KNOWLEDGE-BASE/CONTEXT/PATTERNS/*/*.md`.
        kp = tmp_path / "KNOWLEDGE-BASE" / "CONTEXT" / "PATTERNS" / "common"
        kp.mkdir(parents=True, exist_ok=True)
        (kp / name).write_text(body)

    def test_does_not_flag_both_glyphs_one_line(self, tmp_path):
        # Q4 (unlocked) is NOT implemented: a line legitimately carrying
        # both `→` (routes) and `⇒` (implies) — the glossary's OWN §7
        # canonical pattern — must NOT flag. (Was the 5-FP class.)
        self._mk_glossary(tmp_path)
        self._mk_kb_pattern(
            tmp_path,
            "# P\n\n- s1 → s2 → s3 ⇒ formalize → KB § X.md\n",
        )
        issues = check_doc_symbology_drift(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_single_glyph_per_line(self, tmp_path):
        self._mk_glossary(tmp_path)
        self._mk_kb_pattern(
            tmp_path,
            "# P\n\n- rule → KB § X.md\n- N≥3 ⇒ MUST formalize\n",
        )
        issues = check_doc_symbology_drift(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_prose_minus_sign(self, tmp_path):
        # The testing.md:727 live FP: `−848 LOC` uses U+2212 MINUS SIGN
        # (a math-block glyph) as arithmetic prose, not invented symbology.
        self._mk_glossary(tmp_path)
        self._mk_kb_pattern(
            tmp_path, "# P\n\n- Net: −848 LOC product code, +316 seed-lib\n",
        )
        issues = check_doc_symbology_drift(tmp_path)
        assert issues == [], issues

    def test_flags_out_of_glossary_symbology_glyph(self, tmp_path):
        self._mk_glossary(tmp_path)
        # ⊕ is a math-operator-class glyph NOT in the minimal glossary.
        self._mk_kb_pattern(tmp_path, "# P\n\n- a ⊕ b is undefined\n")
        issues = check_doc_symbology_drift(tmp_path)
        offenders = [i for i in issues if "Inventing new symbols" in i["issue"]]
        assert len(offenders) == 1, issues
        assert "⊕" in offenders[0]["issue"]
        assert offenders[0]["severity"] == "warning"

    def test_does_not_flag_glossary_member(self, tmp_path):
        self._mk_glossary(tmp_path)
        self._mk_kb_pattern(
            tmp_path, "# P\n\n- test green ∧ build passes ∨ skip\n",
        )
        issues = check_doc_symbology_drift(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_glyph_in_inline_code(self, tmp_path):
        self._mk_glossary(tmp_path)
        # `⊕` shown AS an inline-code example is documentation, not use.
        self._mk_kb_pattern(
            tmp_path, "# P\n\n- the `⊕` glyph would be undefined here\n",
        )
        issues = check_doc_symbology_drift(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_inside_fenced_code(self, tmp_path):
        self._mk_glossary(tmp_path)
        self._mk_kb_pattern(
            tmp_path,
            "# P\n\n```\nx → y ⇒ z and ⊕ raw\n```\n",
        )
        issues = check_doc_symbology_drift(tmp_path)
        assert issues == [], issues

    def test_does_not_scan_glossary_itself(self, tmp_path):
        # The glossary legitimately lists every symbol + counter-examples.
        self._mk_glossary(tmp_path)
        issues = check_doc_symbology_drift(tmp_path)
        assert issues == [], issues

    def test_status_emoji_out_of_glossary_flagged(self, tmp_path):
        self._mk_glossary(tmp_path)
        # 🗑 is a status-class emoji NOT in the minimal glossary above.
        self._mk_kb_pattern(tmp_path, "# P\n\n- archived 🗑 here\n")
        issues = check_doc_symbology_drift(tmp_path)
        offenders = [i for i in issues if "🗑" in i["issue"]]
        assert len(offenders) == 1, issues

    def test_decorative_emoji_not_treated_as_symbology(self, tmp_path):
        self._mk_glossary(tmp_path)
        # 🚀 is NOT status-class — prose decoration, must not flag.
        self._mk_kb_pattern(tmp_path, "# P\n\n- shipped it 🚀 today\n")
        issues = check_doc_symbology_drift(tmp_path)
        assert issues == [], issues

    def test_unparseable_glossary_emits_parse_warning(self, tmp_path):
        # §8 contract: surface the parse failure, not phantom drift.
        self._mk_glossary(tmp_path, "# Doc Symbology\n\nNo tables here.\n")
        self._mk_kb_pattern(tmp_path, "# P\n\n- a ⊕ b ⇒ → mixed\n")
        issues = check_doc_symbology_drift(tmp_path)
        assert len(issues) == 1, issues
        assert "unparseable" in issues[0]["issue"]
        assert issues[0]["severity"] == "warning"

    def test_no_glossary_no_enforcement(self, tmp_path):
        self._mk_kb_pattern(tmp_path, "# P\n\n- a ⊕ b ⇒ → mixed\n")
        issues = check_doc_symbology_drift(tmp_path)
        assert issues == [], issues

    def test_missing_repo_root_no_error(self, tmp_path):
        issues = check_doc_symbology_drift(tmp_path / "nope")
        assert issues == []

    def test_claude_md_in_scope(self, tmp_path):
        self._mk_glossary(tmp_path)
        # An out-of-glossary glyph (⊗) in CLAUDE.md (a scoped surface).
        (tmp_path / "CLAUDE.md").write_text(
            "# CLAUDE\n\n- a ⊗ b is not a defined symbol\n"
        )
        issues = check_doc_symbology_drift(tmp_path)
        assert any(
            i["file"] == "CLAUDE.md" and "⊗" in i["issue"] for i in issues
        ), issues

    def test_readme_narrative_out_of_scope(self, tmp_path):
        self._mk_glossary(tmp_path)
        prod = tmp_path / "products" / "p1"
        prod.mkdir(parents=True)
        # README is NOT in _SYMBOLOGY_DOC_GLOBS — glossary §3.
        (prod / "README.md").write_text("# R\n\n- a ⊕ b is free prose\n")
        issues = check_doc_symbology_drift(tmp_path)
        assert issues == [], issues

    def test_unparseable_glossary_test_uses_out_of_glossary(self, tmp_path):
        # Sanity: the unparseable path short-circuits regardless of doc
        # content (already covered above; this pins the early-return).
        # 2026-05-26 PATTERNS reorg: glossary moved into common/.
        gp = tmp_path / "KNOWLEDGE-BASE" / "CONTEXT" / "PATTERNS" / "common"
        gp.mkdir(parents=True)
        (gp / "doc-symbology.md").write_text("# no tables\n")
        (gp / "x.md").write_text("# P\n\n- a ⊗ b\n")
        issues = check_doc_symbology_drift(tmp_path)
        assert len(issues) == 1 and "unparseable" in issues[0]["issue"]


# ---------------------------------------------------------------------------
# check_dockerfile_vite_supabase_args
# ---------------------------------------------------------------------------

_GOOD_DOCKERFILE = """# syntax=docker/dockerfile:1.7
FROM noctus-seed-frontend-base:dev AS frontend-build
WORKDIR /app
ARG VITE_SUPABASE_URL=
ENV VITE_SUPABASE_URL=${VITE_SUPABASE_URL}
ARG VITE_SUPABASE_PUBLISHABLE_KEY=
ENV VITE_SUPABASE_PUBLISHABLE_KEY=${VITE_SUPABASE_PUBLISHABLE_KEY}
COPY products/p1/frontend ./
RUN npm run build

FROM noctus-seed-backend-base:dev AS runtime
WORKDIR /app
"""

_GOOD_COMPOSE = """services:
  p1:
    build:
      context: ../..
      dockerfile: products/p1/backend/Dockerfile
      target: runtime-watch
      args:
        VITE_SUPABASE_URL: ${VITE_SUPABASE_URL:-}
        VITE_SUPABASE_PUBLISHABLE_KEY: ${VITE_SUPABASE_PUBLISHABLE_KEY:-}
    container_name: noctus-p1
networks:
  noctus-net:
    name: noctus-net
    external: true
"""


class TestCheckDockerfileViteSupabaseArgs:
    """Every product backend Dockerfile that builds the SPA must bake the
    boot-critical VITE_SUPABASE_* args (Dockerfile ARG/ENV + compose args).
    """

    def _mk_product(
        self,
        tmp_path: Path,
        slug: str,
        dockerfile: str,
        compose: str | None,
    ) -> None:
        be = tmp_path / "products" / slug / "backend"
        be.mkdir(parents=True)
        (be / "Dockerfile").write_text(dockerfile)
        if compose is not None:
            (tmp_path / "products" / slug / "docker-compose.yml").write_text(
                compose
            )

    def test_clean_product_no_issues(self, tmp_path):
        self._mk_product(tmp_path, "p1", _GOOD_DOCKERFILE, _GOOD_COMPOSE)
        issues = check_dockerfile_vite_supabase_args(tmp_path)
        assert issues == [], issues

    def test_flags_missing_arg_in_dockerfile(self, tmp_path):
        df = _GOOD_DOCKERFILE.replace(
            "ARG VITE_SUPABASE_PUBLISHABLE_KEY=\n"
            "ENV VITE_SUPABASE_PUBLISHABLE_KEY="
            "${VITE_SUPABASE_PUBLISHABLE_KEY}\n",
            "",
        )
        self._mk_product(tmp_path, "p1", df, _GOOD_COMPOSE)
        issues = check_dockerfile_vite_supabase_args(tmp_path)
        df_issues = [i for i in issues if i["file"].endswith("Dockerfile")]
        assert len(df_issues) == 1, issues
        assert df_issues[0]["severity"] == "error"
        assert "VITE_SUPABASE_PUBLISHABLE_KEY" in df_issues[0]["issue"]
        assert df_issues[0]["product"] == "p1"

    def test_flags_arg_after_build_line(self, tmp_path):
        # ARG/ENV present but AFTER `npm run build` → too late, Vite
        # already inlined empty.
        df = (
            "FROM base AS frontend-build\n"
            "RUN npm run build\n"
            "ARG VITE_SUPABASE_URL=\n"
            "ENV VITE_SUPABASE_URL=${VITE_SUPABASE_URL}\n"
            "ARG VITE_SUPABASE_PUBLISHABLE_KEY=\n"
            "ENV VITE_SUPABASE_PUBLISHABLE_KEY="
            "${VITE_SUPABASE_PUBLISHABLE_KEY}\n"
            "FROM base AS runtime\n"
        )
        self._mk_product(tmp_path, "p1", df, _GOOD_COMPOSE)
        issues = check_dockerfile_vite_supabase_args(tmp_path)
        df_issues = [i for i in issues if i["file"].endswith("Dockerfile")]
        assert len(df_issues) == 2, issues  # both vars after build
        assert all(i["severity"] == "error" for i in df_issues)

    def test_flags_missing_compose_arg(self, tmp_path):
        comp = _GOOD_COMPOSE.replace(
            "        VITE_SUPABASE_PUBLISHABLE_KEY: "
            "${VITE_SUPABASE_PUBLISHABLE_KEY:-}\n",
            "",
        )
        self._mk_product(tmp_path, "p1", _GOOD_DOCKERFILE, comp)
        issues = check_dockerfile_vite_supabase_args(tmp_path)
        comp_issues = [
            i for i in issues if i["file"].endswith("docker-compose.yml")
        ]
        assert len(comp_issues) == 1, issues
        assert comp_issues[0]["severity"] == "error"
        assert "VITE_SUPABASE_PUBLISHABLE_KEY" in comp_issues[0]["issue"]

    def test_flags_missing_compose_file(self, tmp_path):
        self._mk_product(tmp_path, "p1", _GOOD_DOCKERFILE, None)
        issues = check_dockerfile_vite_supabase_args(tmp_path)
        assert len(issues) == 1, issues
        assert "docker-compose.yml` is missing" in issues[0]["issue"]
        assert issues[0]["severity"] == "error"

    def test_backend_only_product_out_of_scope(self, tmp_path):
        # No vite/npm build in the Dockerfile → not in scope, no compose
        # requirement.
        df = (
            "FROM noctus-seed-backend-base:dev AS runtime\n"
            "WORKDIR /app\n"
            'CMD ["uvicorn", "app.main:app"]\n'
        )
        self._mk_product(tmp_path, "p1", df, None)
        issues = check_dockerfile_vite_supabase_args(tmp_path)
        assert issues == [], issues

    def test_compose_list_style_args_recognized(self, tmp_path):
        comp = _GOOD_COMPOSE.replace(
            "      args:\n"
            "        VITE_SUPABASE_URL: ${VITE_SUPABASE_URL:-}\n"
            "        VITE_SUPABASE_PUBLISHABLE_KEY: "
            "${VITE_SUPABASE_PUBLISHABLE_KEY:-}\n",
            "      args:\n"
            "        - VITE_SUPABASE_URL=${VITE_SUPABASE_URL:-}\n"
            "        - VITE_SUPABASE_PUBLISHABLE_KEY="
            "${VITE_SUPABASE_PUBLISHABLE_KEY:-}\n",
        )
        self._mk_product(tmp_path, "p1", _GOOD_DOCKERFILE, comp)
        issues = check_dockerfile_vite_supabase_args(tmp_path)
        assert issues == [], issues

    def test_no_products_dir_no_error(self, tmp_path):
        issues = check_dockerfile_vite_supabase_args(tmp_path)
        assert issues == []

    def test_missing_repo_root_no_error(self, tmp_path):
        issues = check_dockerfile_vite_supabase_args(tmp_path / "nope")
        assert issues == []
