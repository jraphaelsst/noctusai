"""The embedding-cache-gate trigger scope must match what the caches index.

WHY (2026-08-11). `embedding-cache-gate.yml` triggered on a bare `products/seed/**`,
so every npm dependency PR touching `products/seed/frontend/package.json` fired the
whole job — apt + pip install + cache gates — for a file the embedding caches cannot
see. Worse, dependabot PRs get no repo secrets, so the tunnel is skipped and the run
cannot do real validation anyway; it just burned CI and painted the PR red for a
reason unrelated to the bump. Four of the nine red dependabot PRs that day were
exactly this, all `products/seed/frontend/*`.

Same class as the two scope errors already catalogued this session (hound reading
only `tools/`, the marker scan reading archived `.patch` files): **a scanner's — or
a trigger's — scope IS its contract.**
→ KB § PATTERNS/devops/prod-deploy-safety-gates.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github" / "workflows" / "embedding-cache-gate.yml"


def _trigger_paths() -> list[str]:
    """The `on.pull_request.paths` entries (the `- "…"` list under `paths:`)."""
    text = WORKFLOW.read_text(encoding="utf-8")
    m = re.search(r"^    paths:\n((?:\s*-\s*\"[^\"]+\"\n)+)", text, re.MULTILINE)
    assert m, "could not locate on.pull_request.paths in embedding-cache-gate.yml"
    return re.findall(r'-\s*"([^"]+)"', m.group(1))


class TestTriggerScope:
    def test_no_bare_products_seed_glob(self):
        """🔴 The regression: `products/seed/**` matches package.json + lockfiles."""
        paths = _trigger_paths()
        assert "products/seed/**" not in paths, (
            "a bare products/seed/** fires this gate for npm-only PRs the embedding "
            "caches cannot see — scope it to the indexed extensions"
        )

    def test_every_path_is_extension_scoped(self):
        """No entry may end in a bare `**` — that is how the false-red got in."""
        offenders = [p for p in _trigger_paths() if p.endswith("/**") or p == "**"]
        assert not offenders, f"unscoped trigger path(s): {offenders}"

    def test_covers_the_extensions_the_caches_actually_index(self):
        paths = _trigger_paths()
        for required in ("KNOWLEDGE-BASE/**/*.md", "mcp/**/*.py", "noctusai_lib/**/*.py"):
            assert required in paths, f"{required} must still trigger the gate"
        # seed source still matters — it feeds code-embeddings.
        assert any(p.startswith("products/seed/") and p.endswith(".py") for p in paths)
        assert any(p.startswith("products/seed/") and p.endswith(".tsx") for p in paths)

    def test_trigger_extensions_match_code_embeddings(self):
        """Keep the workflow and `code_embeddings` in step — widening one without
        the other silently re-opens the false-red (or drops real coverage)."""
        from tools.noctus.dev.code_embeddings import _PY_EXTS, _TS_EXTS

        indexed = {e.lstrip(".") for e in _PY_EXTS + _TS_EXTS}
        seed_exts = {
            p.rsplit(".", 1)[-1] for p in _trigger_paths()
            if p.startswith("products/seed/")
        }
        assert seed_exts == indexed, (
            f"seed trigger extensions {sorted(seed_exts)} != code-embeddings "
            f"indexed extensions {sorted(indexed)}"
        )


class TestNpmOnlyPrWouldNotTrigger:
    """Simulate the four PRs that were red for no reason."""

    def _matches(self, changed: str, pattern: str) -> bool:
        # Translate the GitHub path glob to a regex: ** spans directories, * does not.
        rx = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        return re.fullmatch(rx, changed) is not None

    def _fires(self, changed: str) -> bool:
        return any(self._matches(changed, p) for p in _trigger_paths())

    def test_seed_frontend_package_json_does_not_fire(self):
        assert not self._fires("products/seed/frontend/package.json")

    def test_seed_frontend_lockfile_does_not_fire(self):
        assert not self._fires("products/seed/frontend/package-lock.json")

    def test_seed_frontend_source_still_fires(self):
        assert self._fires("products/seed/frontend/src/App.tsx")

    def test_seed_backend_python_still_fires(self):
        assert self._fires("products/seed/backend/main.py")

    def test_kb_doc_still_fires(self):
        assert self._fires("KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md")

    def test_mcp_python_still_fires(self):
        assert self._fires("mcp/noctusai/tools/noctus/dev/code_embeddings.py")
