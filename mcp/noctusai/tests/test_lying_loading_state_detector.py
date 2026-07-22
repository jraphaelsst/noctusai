"""Regression tests for check_lying_loading_state.

TanStack Query v5 `isLoading === isPending && isFetching` — FALSE during a
background refetch. A UI gated on `.isLoading` (JSX prop, or a hand-rolled
`!X.isLoading && ... .length === 0` guard) falls through to its EMPTY branch
mid-refetch, rendering "no data" over live data. Live incident 2026-07-21/22
(social-wiring Leads, 12,177 leads / 28 brokers, fixed b0cb47b1 + ae9087ce).

Fixtures below are the EXACT pre-fix / post-fix shapes pulled from git
history (`git show ae9087ce:.../Corretores.tsx` and `git show ae9087ce^:
.../Corretores.tsx`), not paraphrases — a detector regression-tested against
a paraphrase can silently drift from the real bug shape.

KB § PATTERNS/frontend/lying-loading-state.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_lying_loading_state


def _make_repo(tmp: Path) -> Path:
    (tmp / "products").mkdir(parents=True, exist_ok=True)
    return tmp


def _product_file(repo: Path, slug: str, rel: str, content: str) -> Path:
    target = repo / "products" / slug / "frontend" / "src" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# The exact pre-fix ChartCard usage — `git show ae9087ce:products/
# social-wiring/frontend/src/pages/leads/Corretores.tsx` (before b0cb47b1).
_POSITIVE_CHARTCARD_PROP = """\
export default function Corretores() {
  const byDimQ = useLeadsByDimension(filters, { dim: "corretor", limit: 50 });
  const rankedBuckets = [...buckets].sort((a, b) => b.total - a.total).slice(0, 15);

  return (
    <div className="space-y-4">
      <ChartCard
        title="Ranking de corretores"
        subtitle="Total de leads no período selecionado."
        loading={byDimQ.isLoading}
        error={byDimQ.isError ? "Erro ao carregar o ranking." : null}
        isEmpty={rankedBuckets.length === 0}
      >
        <BarChart data={rankedBuckets} xKey="label" series={[{ key: "total", label: "Leads" }]} />
      </ChartCard>
    </div>
  );
}
"""

# The exact pre-fix hand-rolled empty-state guard — `git show ae9087ce^:
# products/social-wiring/frontend/src/pages/leads/Corretores.tsx` (before
# ae9087ce, which fixed this shape one commit earlier than b0cb47b1).
_POSITIVE_HANDROLLED_GUARD = """\
export default function Corretores() {
  const byDimQ = useLeadsByDimension(filters, { dim: "corretor", limit: 50 });
  const buckets = byDimQ.data?.buckets ?? [];

  return (
    <div className="rounded-lg border border-border bg-card">
      {byDimQ.isLoading && (
        <div className="p-4 text-sm text-muted-foreground">Carregando...</div>
      )}
      {byDimQ.isError && (
        <div className="p-4 text-sm text-destructive">Erro ao carregar corretores.</div>
      )}
      {!byDimQ.isLoading && !byDimQ.isError && buckets.length === 0 && (
        <div className="p-4 text-center text-sm text-muted-foreground">
          Sem dados para o período selecionado.
        </div>
      )}
    </div>
  );
}
"""

# The FIXED shape — `git show b0cb47b1:...Corretores.tsx` — MUST NOT flag.
_NEGATIVE_CORRECT_GATE = """\
export default function Corretores() {
  const byDimQ = useLeadsByDimension(filters, { dim: "corretor", limit: 50 });
  const rankedBuckets = [...buckets].sort((a, b) => b.total - a.total).slice(0, 15);
  const buckets = byDimQ.data?.buckets ?? [];

  return (
    <div className="space-y-4">
      <ChartCard
        title="Ranking de corretores"
        subtitle="Total de leads no período selecionado."
        loading={byDimQ.isPending || byDimQ.isFetching}
        error={byDimQ.isError ? "Erro ao carregar o ranking." : null}
        isEmpty={rankedBuckets.length === 0}
      >
        <BarChart data={rankedBuckets} xKey="label" series={[{ key: "total", label: "Leads" }]} />
      </ChartCard>

      {!byDimQ.isPending && !byDimQ.isFetching && !byDimQ.isError && buckets.length === 0 && (
        <div className="p-4 text-center text-sm text-muted-foreground">
          Sem dados para o período selecionado.
        </div>
      )}
    </div>
  );
}
"""

# A plain, unrelated `loading` prop (a local boolean, not a TanStack query
# member expression) — MUST NOT flag.
_NEGATIVE_PLAIN_BOOLEAN = """\
export default function SubmitButton() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  return (
    <Button loading={isSubmitting} onClick={() => setIsSubmitting(true)}>
      Save
    </Button>
  );
}
"""


class TestLyingLoadingState:
    def test_positive_chartcard_prop_shape_flagged(self, tmp_path):
        """`git show ae9087ce:.../Corretores.tsx` — loading={q.isLoading}
        paired with isEmpty= on the same ChartCard tag MUST be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "social-wiring", "pages/leads/Corretores.tsx", _POSITIVE_CHARTCARD_PROP)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "the exact pre-fix ChartCard shape must be flagged"
        assert any("byDimQ.isLoading" in i["issue"] for i in issues)
        # The higher-value (paired isEmpty=) message must be the one that fires.
        assert any("isEmpty=" in i["issue"] or "empty=" in i["issue"] for i in issues)
        assert all(i["severity"] == "warning" for i in issues)

    def test_positive_handrolled_guard_shape_flagged(self, tmp_path):
        """`git show ae9087ce^:.../Corretores.tsx` — the hand-rolled
        `!X.isLoading && ... && rows.length === 0` guard MUST be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "social-wiring", "pages/leads/Corretores.tsx", _POSITIVE_HANDROLLED_GUARD)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "the exact pre-fix hand-rolled guard must be flagged"
        assert any("hand-rolled empty-state guard" in i["issue"] for i in issues)

    def test_negative_correct_gate_not_flagged(self, tmp_path):
        """The FIXED shape (`b0cb47b1` + `ae9087ce`) — isPending || isFetching
        — must NOT be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "social-wiring", "pages/leads/Corretores.tsx", _NEGATIVE_CORRECT_GATE)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"fixed isPending||isFetching shape must not be flagged: {issues}"

    def test_negative_plain_boolean_prop_not_flagged(self, tmp_path):
        """An unrelated `loading` prop bound to a plain local boolean (no
        `.isLoading` member access) must NOT false-positive."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "some-product", "components/SubmitButton.tsx", _NEGATIVE_PLAIN_BOOLEAN)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"plain boolean loading prop must not be flagged: {issues}"

    def test_escape_hatch_suppresses(self, tmp_path):
        """`lying-loading-ok` on a preceding line suppresses the finding."""
        repo = _make_repo(tmp_path)
        content = (
            "export default function X() {\n"
            "  // lying-loading-ok: query is a Fake with no refetch semantics\n"
            "  return <ChartCard loading={q.isLoading} isEmpty={rows.length === 0} />;\n"
            "}\n"
        )
        _product_file(repo, "some-product", "components/X.tsx", content)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"escape-hatched line must not be flagged: {issues}"

    def test_no_products_dir_returns_empty(self, tmp_path):
        """No `products/` dir on disk → empty, no crash."""
        issues = check_lying_loading_state(repo_root=tmp_path)
        assert issues == []
