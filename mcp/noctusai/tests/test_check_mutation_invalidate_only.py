"""`check_mutation_invalidate_only` — a TanStack mutation must put what it knows into the cache
(optimistic `onMutate` and/or `setQueryData` with the server's answer), not only invalidate. A
per-file RATCHET baseline lets the pre-existing ones through; only NEW ones block, and a lowered
count must lower the baseline.

→ KB § PATTERNS/frontend/mutation-cache-writes.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    REPO_ROOT,
    check_mutation_invalidate_only,
    mutation_invalidate_only_counts,
    mutation_invalidate_only_hits,
)

HOOKS = "products/demo/frontend/src/hooks/useThings.ts"
BASELINE = "mcp/noctusai/tests/mutation_invalidate_only_baseline.json"

INVALIDATE_ONLY = """
export function useAddThing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: Thing) => api.post("/api/things", p),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["things"] }); },
  });
}
"""

WRITES_RESULT = """
export function useAddThing() {
  const qc = useQueryClient();
  return useMutation<Thing, Error, Thing>({
    mutationFn: (p) => api.post("/api/things", p),
    onSuccess: (saved) => { qc.setQueryData(["things"], (old: Thing[] = []) => [...old, saved]); },
  });
}
"""

OPTIMISTIC = """
export function useToggle() {
  return useMutation({
    mutationFn: (id: string) => api.patch(`/api/things/${id}`),
    onMutate: async (id) => { /* draw */ },
  });
}
"""


def _tree(root: Path, files: dict[str, str], baseline: dict[str, int] | None = None) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    b = root / BASELINE
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text(json.dumps({"arquivos": baseline or {}}), encoding="utf-8")
    return root


class TestCheckMutationInvalidateOnly:
    def test_invalidate_only_mutation_is_flagged(self, tmp_path):
        _tree(tmp_path, {HOOKS: INVALIDATE_ONLY})
        issues = check_mutation_invalidate_only(tmp_path)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high" and issues[0]["product"] == "demo"
        assert "useCacheWriteMutation" in issues[0]["issue"]

    def test_writing_the_result_or_drawing_optimistically_passes(self, tmp_path):
        _tree(tmp_path, {HOOKS: WRITES_RESULT + OPTIMISTIC})
        assert check_mutation_invalidate_only(tmp_path) == []

    def test_the_seed_primitive_is_not_a_raw_usemutation(self, tmp_path):
        text = 'return useCacheWriteMutation<Thing, Thing>({ mutationFn: f, targets: [] });\n'
        _tree(tmp_path, {HOOKS: text})
        assert check_mutation_invalidate_only(tmp_path) == []

    def test_baselined_count_passes_and_one_more_blocks(self, tmp_path):
        _tree(tmp_path, {HOOKS: INVALIDATE_ONLY}, {HOOKS: 1})
        assert check_mutation_invalidate_only(tmp_path) == []
        _tree(tmp_path, {HOOKS: INVALIDATE_ONLY * 2}, {HOOKS: 1})
        assert len(check_mutation_invalidate_only(tmp_path)) == 1

    def test_a_lowered_count_must_lower_the_baseline(self, tmp_path):
        _tree(tmp_path, {HOOKS: WRITES_RESULT}, {HOOKS: 2})
        issues = check_mutation_invalidate_only(tmp_path)
        assert len(issues) == 1 and "lower" in issues[0]["issue"]

    def test_escape_marker_on_the_usemutation_line(self, tmp_path):
        text = INVALIDATE_ONLY.replace(
            "return useMutation({", "return useMutation({ // noc-allow: invalidate-only — server regroups the view"
        )
        _tree(tmp_path, {HOOKS: text})
        assert check_mutation_invalidate_only(tmp_path) == []

    def test_tests_are_out_of_scope(self, tmp_path):
        _tree(tmp_path, {"products/demo/frontend/src/hooks/__tests__/x.test.ts": INVALIDATE_ONLY})
        assert check_mutation_invalidate_only(tmp_path) == []

    def test_hits_report_the_usemutation_line(self):
        assert mutation_invalidate_only_hits(INVALIDATE_ONLY) == [4]

    def test_committed_baseline_matches_the_tree(self):
        """The shipped baseline is exactly the live tree — the ratchet starts from truth."""
        baseline = json.loads((REPO_ROOT / BASELINE).read_text(encoding="utf-8"))["arquivos"]
        assert baseline == mutation_invalidate_only_counts(REPO_ROOT)
