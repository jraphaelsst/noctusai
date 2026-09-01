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

`TestLyingLoadingStateModeB` below covers the 2026-08-31 skeleton-over-data /
refetch-unmount class (AST-scanned via `mcp/noctusai/node/
lying_loading_scan.mjs`, ts-morph) — requires `node` + `mcp/noctusai/node/
node_modules` (`cd mcp/noctusai/node && npm install`); skipped, not silently
passed, when either is unavailable in this environment.

KB § PATTERNS/frontend/lying-loading-state.md
"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    _LYING_LOADING_MODEB_SCRIPT,
    check_lying_loading_state,
)

_MODEB_TOOLING_AVAILABLE = (
    shutil.which("node") is not None
    and _LYING_LOADING_MODEB_SCRIPT.exists()
    and (_LYING_LOADING_MODEB_SCRIPT.parent / "node_modules" / "ts-morph").exists()
)
_modeb_only = pytest.mark.skipif(
    not _MODEB_TOOLING_AVAILABLE,
    reason=(
        "node / ts-morph unavailable — run `cd mcp/noctusai/node && npm install` "
        "to provision Mode B tooling"
    ),
)


def _make_repo(tmp: Path) -> Path:
    (tmp / "products").mkdir(parents=True, exist_ok=True)
    return tmp


def _product_file(repo: Path, slug: str, rel: str, content: str) -> Path:
    target = repo / "products" / slug / "frontend" / "src" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _drop_modeb_tooling_meta_findings(issues: list[dict]) -> list[dict]:
    """Filter out the Mode-B "the AST scan tooling itself couldn't run"
    meta-finding (`node`/`ts-morph` unavailable — see
    `_run_lying_loading_modeb_scan`'s docstring).

    `TestLyingLoadingState` below tests MODE A ONLY and must stay accurate
    regardless of whether `mcp/noctusai/node/node_modules` happens to be
    provisioned in the environment running this file (CI's `ubuntu-latest`
    runner ships `node` but nothing installs `mcp/noctusai/node`'s
    `node_modules` today — a real gap, see this dispatch's `drift-found`
    trailer). The bootstrap-error / parse-error path itself has its OWN
    dedicated, explicit test
    (`TestLyingLoadingStateModeB::test_modeb_bootstrap_error_surfaces_as_one_explicit_finding`)
    — filtering it out HERE does not hide it from the suite, it just keeps
    the Mode-A assertions from depending on Node tooling they don't need.
    """
    return [
        i for i in issues
        if "AST scan could not run" not in i["issue"] and "AST scan could not parse" not in i["issue"]
    ]


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
        issues = _drop_modeb_tooling_meta_findings(check_lying_loading_state(repo_root=repo))
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
        issues = _drop_modeb_tooling_meta_findings(check_lying_loading_state(repo_root=repo))
        assert issues == [], f"escape-hatched line must not be flagged: {issues}"

    def test_no_products_dir_returns_empty(self, tmp_path):
        """No `products/` dir on disk → empty, no crash."""
        issues = check_lying_loading_state(repo_root=tmp_path)
        assert issues == []


# ===========================================================================
# Mode B — skeleton-over-data / refetch-unmount (2026-08-31 fleet audit).
# AST-scanned via `mcp/noctusai/node/lying_loading_scan.mjs`; every positive
# fixture must be flagged AND (per the task's zero-false-positive gate) every
# negative fixture must produce EXACTLY ZERO issues.
# ===========================================================================

# The EXACT shape that shipped 2026-08-31 (this dispatch's own regression
# fixture, per the brief) — the fix for Mode A applied literally.
_MODEB_POSITIVE_EARLY_RETURN = """\
export function LeadsPanel() {
  const { isPending, isFetching, data } = useLeads();
  if (isPending || isFetching) return <Skeleton />;
  return <div>{data}</div>;
}
"""

# One-hop local-variable alias (the `products/p-studio/frontend/src/pages/
# Integracoes.tsx` shape, but WITHOUT the `&& !data` guard the real file
# carries at the use site — this variant IS a real bug).
_MODEB_POSITIVE_DERIVED_VAR = """\
export function Equipe() {
  const membersQuery = useMembers();
  const loading = membersQuery.isPending || membersQuery.isFetching;

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }
  return <div>{membersQuery.data}</div>;
}
"""

# JSX ternary at CHILD position — unmounts one branch for the other, exactly
# the `products/social-wiring/frontend/src/pages/meta/AdDetalheModal.tsx`
# shape found live by the fleet scan below.
_MODEB_POSITIVE_JSX_TERNARY = """\
export function Chart() {
  const seriesQ = useSeries();
  const loadingChart = seriesQ.isPending || seriesQ.isFetching;
  return (
    <div>
      {loadingChart ? (
        <div className="h-56">Carregando…</div>
      ) : (
        <RealChart data={seriesQ.data} />
      )}
    </div>
  );
}
"""

# `return <cond> ? <A/> : <B/>;` — the whole-component-body ternary form of
# the same bug (no JSX-child wrapper, the `return` argument IS the ternary).
_MODEB_POSITIVE_RETURN_TERNARY = """\
export function Panel() {
  const { isFetching, data } = usePanel();
  return isFetching ? <Skeleton /> : <Real data={data} />;
}
"""

# Correct two-signal gate — `showSkeleton = isPending && !data` — MUST NOT
# be flagged.
_MODEB_NEGATIVE_TWO_SIGNAL_GATE = """\
export function LeadsPanel() {
  const { isPending, data } = useLeads();
  if (isPending && !data) return <Skeleton />;
  return <div>{data}</div>;
}
"""

# Canonical in-tree safe form (`products/orbity/frontend/src/pages/
# Funil.tsx:733`) — `isFetching` admitted ONLY while nothing is on screen.
_MODEB_NEGATIVE_CANONICAL_EMPTY_GUARDED = """\
export function Funil() {
  const { isPending, isFetching, stages } = useFunil();
  if (isPending || (isFetching && stages.length === 0)) return <Skeleton />;
  return <div>{stages}</div>;
}
"""

# One-hop derived variable, guarded AT THE USE SITE (not at the declaration)
# — the REAL `products/p-studio/frontend/src/pages/Integracoes.tsx` shape.
# `carregando` itself is declared unguarded; `carregando && !data` at the
# `if` is what makes it safe. MUST NOT be flagged.
_MODEB_NEGATIVE_DERIVED_VAR_GUARDED_AT_USE = """\
export function Integracoes() {
  const { isPending, isFetching, data } = useCredenciais();
  const carregando = isPending || isFetching;
  if (carregando && !data) return <Spinner />;
  return <div>{data}</div>;
}
"""

# `isFetching` as a spinner / opacity / disabled attribute — the explicitly
# ALLOWED non-destructive uses. MUST NOT be flagged.
_MODEB_NEGATIVE_SPINNER_ATTRIBUTE = """\
export function Header() {
  const { isFetching } = useHeader();
  return (
    <div
      spinner={isFetching}
      className={isFetching ? "opacity-60" : ""}
    >
      <SaveButton disabled={isFetching} />
    </div>
  );
}
"""

# `isFetching && !!data` as a non-destructive JSX-child indicator (never an
# early return) — the canonical `isRefreshing` shape. MUST NOT be flagged.
_MODEB_NEGATIVE_NONDESTRUCTIVE_INDICATOR = """\
export function LeadsPanel() {
  const { isPending, isFetching, data } = useLeads();
  if (isPending && !data) return <Skeleton />;
  return (
    <div>
      {isFetching && !!data && <Spinner size="sm" />}
      {data}
    </div>
  );
}
"""

# A MUTATION's `isPending` (not a query's) — no `data` concept at all. The
# real `products/erp-imobiliario/frontend/src/components/clientes/
# LeadScoreBadge.tsx:49` shape. MUST NOT be flagged (bare `isPending` alone,
# with no `isFetching`, is out of Mode B's scope by design — see
# `check_lying_loading_state`'s docstring).
_MODEB_NEGATIVE_MUTATION_ISPENDING = """\
export function LeadScoreBadge() {
  const { mutate, isPending } = useLeadScore();
  if (isPending) {
    return <Badge>Analisando...</Badge>;
  }
  return <Badge>Done</Badge>;
}
"""

_MODEB_ESCAPE_HATCHED = """\
export function FakeDouble() {
  // lying-loading-ok: Fake test double, not a real TanStack query
  if (isPending || isFetching) return <Skeleton />;
  return <div>ok</div>;
}
"""

# ---------------------------------------------------------------------------
# Shape 5 — bare `.isLoading` reaching an early return / ternary directly
# (no JSX `loading=` prop wrapper — that's Shape 1/2 — and no hand-rolled
# `.length === 0` guard — that's Shape 3). From the orbity sweep: 21/21
# Mode-A fixes in that product were this exact shape, and it fell straight
# out of the idiomatic `const { data, isLoading } = useX();` destructure.
# Guard-agnostic by design — see `check_lying_loading_state`'s docstring.
# ---------------------------------------------------------------------------

_MODEB_POSITIVE_SHAPE5_EARLY_RETURN = """\
export function ProductList() {
  const { data, isLoading } = useProducts();
  if (isLoading) return <Skeleton />;
  return <Table rows={data} />;
}
"""

_MODEB_POSITIVE_SHAPE5_JSX_TERNARY = """\
export function ProductListTernary() {
  const { data, isLoading } = useProducts();
  return (
    <div>
      {isLoading ? <Skeleton /> : <Table rows={data} />}
    </div>
  );
}
"""

# The `q.isLoading` (not destructured) form via a one-hop alias — MUST fire
# regardless of whether `isLoading` is destructured or read as `q.isLoading`.
_MODEB_POSITIVE_SHAPE5_QUALIFIED_VIA_ALIAS = """\
export function ProductListAlias() {
  const q = useProducts();
  const loading = q.isLoading;
  if (loading) return <Skeleton />;
  return <Table rows={q.data} />;
}
"""

# The correct fix — `showSkeleton = isPending && !data`, no `.isLoading` at
# all — MUST NOT be flagged.
_MODEB_NEGATIVE_SHAPE5_CORRECT_GATE = """\
export function ProductListCorrect() {
  const { data, isPending } = useProducts();
  if (isPending && !data) return <Skeleton />;
  return <Table rows={data} />;
}
"""

# The REAL `products/erp-imobiliario/frontend/src/components/modals/
# AdicionarRoleModal.tsx:39` shape, found by the FIRST-pass Shape-5 scan as
# a false positive and fixed same-dispatch: a hand-rolled, ARRAY-destructured
# `useState` local named `isLoading` — no TanStack query, no refetch
# semantics, and the ternary swaps a BUTTON LABEL, not a skeleton over real
# data. MUST NOT be flagged.
_MODEB_NEGATIVE_SHAPE5_USESTATE_LOCAL = """\
export function AddRoleModal() {
  const [isLoading, setIsLoading] = useState(false);

  async function handleAdd() {
    setIsLoading(true);
    await addRole();
    setIsLoading(false);
  }

  return (
    <div>
      <Button disabled={isLoading} onClick={handleAdd}>
        {isLoading ? 'Adicionando...' : 'Adicionar'}
      </Button>
    </div>
  );
}
"""


# ---------------------------------------------------------------------------
# Gap 1 — renamed destructuring bindings. `const { isLoading: contaLoading }
# = useConta();` never produces a text occurrence of the literal `isLoading`
# identifier, so a single-hop early return on the RENAMED local was
# invisible pre-fix. Real-world repro pulled from the dispatch brief
# (personal-finance/pages/ContaDetalhes.tsx pre-fix shape).
# ---------------------------------------------------------------------------
_GAP1_POSITIVE_RENAMED_ISLOADING = """\
export function ContaDetalhes() {
  const { data, isLoading: contaLoading } = useConta();
  if (contaLoading) return <Skeleton />;
  return <Detail conta={data} />;
}
"""

# A renamed `isFetching` (guard-aware) local, UNGUARDED at the use site —
# MUST be flagged, and the message must attribute the `isFetching` taint
# (not `isLoading`) since guard-awareness is inherited from the property
# renamed FROM.
_GAP1_POSITIVE_RENAMED_ISFETCHING_UNGUARDED = """\
export function Panel() {
  const { data, isFetching: loadingWa } = usePanel();
  if (loadingWa) return <Skeleton />;
  return <Real data={data} />;
}
"""

# The SAME renamed `isFetching` local, but guarded `&& !data` at the use
# site — MUST NOT be flagged. Proves the renamed-alias mechanism resolves
# the guard at the USE site through the SAME machinery as the existing
# `const carregando = ...` alias case, not a parallel unguarded path.
_GAP1_NEGATIVE_RENAMED_ISFETCHING_GUARDED = """\
export function Panel() {
  const { data, isFetching: loadingWa } = usePanel();
  if (loadingWa && !data) return <Skeleton />;
  return <Real data={data} />;
}
"""

# A hand-rolled, ARRAY-destructured `useState` local with a renamed-looking
# name — MUST NOT be flagged. Proves the Gap-1 fix does not regress the
# `ObjectBindingPattern`-only restriction: `findRenamedBindingLocals` walks
# ONLY `ObjectBindingPattern` binding elements, and `useState` always
# array-destructures, so no property-name node exists to match against at
# all — this file has no `isLoading`/`isFetching` renamed PROPERTY, just an
# unrelated local variable name.
_GAP1_NEGATIVE_USESTATE_ARRAY_NOT_A_RENAME = """\
export function AddRoleModal() {
  const [loadingLocal, setLoadingLocal] = useState(false);
  return (
    <Button disabled={loadingLocal}>
      {loadingLocal ? 'Adicionando...' : 'Adicionar'}
    </Button>
  );
}
"""


# ---------------------------------------------------------------------------
# Gap 2 — negation stopped the climb. `climb()` had no PrefixUnaryExpression
# case, so a negated occurrence hit the catch-all and never reached the
# ternary/return above it. Real-world repro pulled from the dispatch brief
# (adconnect/pages/Orders.tsx pre-fix shape) — bare destructured `isLoading`,
# so Mode A's `.isLoading`-with-a-dot regex (`_HANDROLLED_LOADING_GUARD_RE`)
# cannot see it either; this is a Mode-B-only gap.
# ---------------------------------------------------------------------------
_GAP2_POSITIVE_NEGATED_ISLOADING_TERNARY = """\
export function Orders() {
  const { data: rows, isLoading } = useOrders();
  return (
    <div>
      {!isLoading && rows.length === 0 ? <Empty /> : <List rows={rows} />}
    </div>
  );
}
"""

# `!!isFetching && !data` — DOUBLE negation must round-trip to the ORIGINAL
# unnegated, protectively-guarded case (`isFetching && !data` is the
# canonical safe shape) — MUST NOT be flagged. Proves the `negated` XOR-flip
# is correct, not a one-shot "seen a `!`" flag.
_GAP2_NEGATIVE_DOUBLE_NEGATION_GUARDED = """\
export function Panel() {
  const { data, isFetching } = usePanel();
  if (!!isFetching && !data) return <Skeleton />;
  return <Real data={data} />;
}
"""

# `!isFetching && !data` — a SINGLE negation of the guard-aware taint. Per
# the module docstring's "INVERTED GUARD UNDER NEGATION" reasoning, a match
# under negation must NEVER grant `guarded = true` (it is not proven safe by
# the same textual match that IS protective in the unnegated case) — so this
# non-canonical shape IS flagged, deliberately, rather than silently trusted.
_GAP2_POSITIVE_NEGATED_ISFETCHING_NOT_RESCUED = """\
export function Panel() {
  const { data, isFetching } = usePanel();
  if (!isFetching && !data) return <Empty />;
  return <Real data={data} />;
}
"""


@_modeb_only
class TestLyingLoadingStateModeB:
    def test_positive_early_return_shipped_shape_flagged(self, tmp_path):
        """The EXACT shape that shipped 2026-08-31 —
        `if (isPending || isFetching) return <Skeleton/>;` — MUST be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "demo", "pages/LeadsPanel.tsx", _MODEB_POSITIVE_EARLY_RETURN)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "the shipped early-return shape must be flagged"
        assert any("early-return" in i["issue"] for i in issues)
        assert all(i["severity"] == "warning" for i in issues)

    def test_positive_derived_variable_unguarded_flagged(self, tmp_path):
        """`const loading = q.isPending || q.isFetching; if (loading)
        return ...;` — unguarded AT THE USE SITE — MUST be flagged, with the
        message identifying the local variable that carried the taint."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "social-wiring", "pages/Equipe.tsx", _MODEB_POSITIVE_DERIVED_VAR)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "unguarded derived-variable early return must be flagged"
        assert any("via local variable `loading" in i["issue"] for i in issues)

    def test_positive_jsx_ternary_flagged(self, tmp_path):
        """`{loadingChart ? <Skeleton/> : <Real/>}` at JSX child position —
        MUST be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "social-wiring", "pages/Chart.tsx", _MODEB_POSITIVE_JSX_TERNARY)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "unguarded JSX ternary must be flagged"
        assert any("JSX ternary" in i["issue"] for i in issues)

    def test_positive_return_ternary_flagged(self, tmp_path):
        """`return isFetching ? <Skeleton/> : <Real/>;` (whole-body ternary,
        no JSX wrapper) — MUST be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "demo", "pages/Panel.tsx", _MODEB_POSITIVE_RETURN_TERNARY)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "unguarded return-ternary must be flagged"
        assert any("whole-body render" in i["issue"] for i in issues)

    def test_negative_two_signal_gate_not_flagged(self, tmp_path):
        """The canonical fix — `isPending && !data` — must NOT be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "demo", "pages/LeadsPanel.tsx", _MODEB_NEGATIVE_TWO_SIGNAL_GATE)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"two-signal gate must not be flagged: {issues}"

    def test_negative_canonical_empty_guarded_not_flagged(self, tmp_path):
        """`isPending || (isFetching && stages.length === 0)` — the in-tree
        canonical form (`Funil.tsx:733`) — must NOT be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "orbity", "pages/Funil.tsx", _MODEB_NEGATIVE_CANONICAL_EMPTY_GUARDED)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"canonical empty-guarded form must not be flagged: {issues}"

    def test_negative_derived_var_guarded_at_use_not_flagged(self, tmp_path):
        """The REAL `Integracoes.tsx` shape — `carregando` declared
        unguarded, guarded with `&& !data` at the `if` — must NOT be
        flagged. This is the case that proves the detector resolves the
        guard at the USE site, not just the declaration."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "p-studio", "pages/Integracoes.tsx", _MODEB_NEGATIVE_DERIVED_VAR_GUARDED_AT_USE)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"use-site-guarded derived variable must not be flagged: {issues}"

    def test_negative_spinner_attribute_not_flagged(self, tmp_path):
        """`spinner=`, `className=` (ternary), `disabled=` — the explicit
        ALLOWED non-destructive attribute uses — must NOT be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "demo", "components/Header.tsx", _MODEB_NEGATIVE_SPINNER_ATTRIBUTE)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"spinner/className/disabled attribute uses must not be flagged: {issues}"

    def test_negative_nondestructive_indicator_not_flagged(self, tmp_path):
        """`isFetching && !!data && <Spinner/>` as a non-destructive JSX
        child indicator (never an early return) — must NOT be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "demo", "pages/LeadsPanel.tsx", _MODEB_NEGATIVE_NONDESTRUCTIVE_INDICATOR)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"non-destructive isFetching && !!data indicator must not be flagged: {issues}"

    def test_negative_mutation_ispending_not_flagged(self, tmp_path):
        """A MUTATION's bare `isPending` (no `isFetching`, no `data`
        concept) — the real `LeadScoreBadge.tsx:49` shape — must NOT be
        flagged. Confirms the deliberate decision NOT to flag bare
        `isPending` (see the detector's docstring)."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "erp-imobiliario", "components/LeadScoreBadge.tsx", _MODEB_NEGATIVE_MUTATION_ISPENDING)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"mutation isPending must not be flagged: {issues}"

    def test_escape_hatch_suppresses_modeb(self, tmp_path):
        """`lying-loading-ok` on a preceding line suppresses a Mode-B
        finding exactly as it does for Mode A."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "demo", "pages/FakeDouble.tsx", _MODEB_ESCAPE_HATCHED)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"escape-hatched Mode B line must not be flagged: {issues}"

    def test_modeb_bootstrap_error_surfaces_as_one_explicit_finding(self, tmp_path, monkeypatch):
        """`node` unavailable → ONE explicit finding naming the failure —
        never a silent zero-findings pass (no-silent-errors, `KB §
        01-PHILOSOPHY.md`)."""
        import tools.noctus.dev.compliance as compliance_module

        repo = _make_repo(tmp_path)
        _product_file(repo, "demo", "pages/LeadsPanel.tsx", _MODEB_POSITIVE_EARLY_RETURN)
        monkeypatch.setattr(compliance_module.shutil, "which", lambda name: None)
        issues = check_lying_loading_state(repo_root=repo)
        assert len(issues) == 1
        assert "AST scan could not run" in issues[0]["issue"]
        assert "node_unavailable" in issues[0]["issue"]

    def test_modeb_per_product_bootstrap_error_scoped_not_global(self, tmp_path, monkeypatch):
        """GAP 3 — one product's Mode-B batch times out (or crashes). MUST
        surface as ONE finding SCOPED to that product (never a global
        `product: "*"`), while a DIFFERENT product's real finding in the
        SAME run is unaffected. Proves the bounded-blast-radius property:
        a pathological product can no longer zero out the whole fleet's
        Mode-B coverage the way the old single-fleet-wide-batch design
        did."""
        import tools.noctus.dev.compliance as compliance_module

        repo = _make_repo(tmp_path)
        _product_file(repo, "flaky-product", "pages/LeadsPanel.tsx", _MODEB_POSITIVE_EARLY_RETURN)
        _product_file(repo, "healthy-product", "pages/LeadsPanel.tsx", _MODEB_POSITIVE_EARLY_RETURN)

        real_fn = compliance_module._run_lying_loading_modeb_scan_one_product

        def _fake_per_product_scan(product, files):
            if product == "flaky-product":
                return {}, {}, "timeout: Mode B AST scan for `flaky-product` exceeded 60s (1 files)"
            return real_fn(product, files)

        monkeypatch.setattr(
            compliance_module, "_run_lying_loading_modeb_scan_one_product", _fake_per_product_scan
        )
        issues = check_lying_loading_state(repo_root=repo)

        assert not any(i["product"] == "*" for i in issues), (
            f"a single product's failure must never degrade to a global '*' finding: {issues}"
        )
        scoped = [
            i for i in issues
            if i["product"] == "flaky-product" and "AST scan for" in i["issue"]
        ]
        assert scoped, f"flaky product's timeout must surface as a scoped finding: {issues}"
        assert any(
            i["product"] == "healthy-product" and "early-return" in i["issue"] for i in issues
        ), f"the healthy product's real finding must still land in the same run: {issues}"

    def test_positive_shape5_bare_islloading_early_return_flagged(self, tmp_path):
        """`if (isLoading) return <Skeleton/>;` (bare destructured, no JSX
        `loading=` prop wrapper) — the shape 21/21 orbity fixes were — MUST
        be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "orbity", "pages/ProductList.tsx", _MODEB_POSITIVE_SHAPE5_EARLY_RETURN)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "bare isLoading early-return must be flagged"
        assert any("Shape 5" in i["issue"] for i in issues)
        assert any("`isLoading`" in i["issue"] for i in issues)

    def test_positive_shape5_jsx_ternary_flagged(self, tmp_path):
        """`{isLoading ? <Skeleton/> : <Table/>}` — the ternary form of
        Shape 5 — MUST be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "orbity", "pages/ProductListTernary.tsx", _MODEB_POSITIVE_SHAPE5_JSX_TERNARY)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "bare isLoading JSX ternary must be flagged"
        assert any("Shape 5" in i["issue"] for i in issues)

    def test_positive_shape5_qualified_via_alias_flagged(self, tmp_path):
        """`q.isLoading` (not destructured) threaded through a one-hop
        local alias — MUST fire regardless of destructured vs. `q.isLoading`
        form."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "orbity", "pages/ProductListAlias.tsx", _MODEB_POSITIVE_SHAPE5_QUALIFIED_VIA_ALIAS)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "q.isLoading via a one-hop alias must be flagged"
        assert any("via local variable `loading" in i["issue"] for i in issues)

    def test_negative_shape5_correct_gate_not_flagged(self, tmp_path):
        """`isPending && !data`, no `.isLoading` anywhere — MUST NOT be
        flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "orbity", "pages/ProductListCorrect.tsx", _MODEB_NEGATIVE_SHAPE5_CORRECT_GATE)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"correct isPending && !data gate must not be flagged: {issues}"

    def test_negative_shape5_usestate_local_not_flagged(self, tmp_path):
        """A hand-rolled, ARRAY-destructured `useState` `isLoading` local
        (no TanStack query, ternary swaps button TEXT not a skeleton) — the
        REAL `AdicionarRoleModal.tsx:39` shape a first-pass Shape-5 scan
        false-positived on — MUST NOT be flagged."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "erp-imobiliario", "components/AddRoleModal.tsx", _MODEB_NEGATIVE_SHAPE5_USESTATE_LOCAL)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"useState-local isLoading must not be flagged: {issues}"

    # -----------------------------------------------------------------
    # Gap 1 — renamed destructuring bindings.
    # -----------------------------------------------------------------

    def test_gap1_positive_renamed_isloading_flagged(self, tmp_path):
        """The REAL `personal-finance/pages/ContaDetalhes.tsx` shape —
        `const { isLoading: contaLoading } = useConta(); if (contaLoading)
        return <Skeleton/>;` — MUST be flagged. Confirmed FAILING against
        the pre-fix scanner (`[]`) before this fix landed."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "personal-finance", "pages/ContaDetalhes.tsx", _GAP1_POSITIVE_RENAMED_ISLOADING)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "renamed isLoading binding must be flagged"
        assert any("Shape 5" in i["issue"] and "contaLoading" in i["issue"] for i in issues)

    def test_gap1_positive_renamed_isfetching_unguarded_flagged(self, tmp_path):
        """A renamed `isFetching` local, UNGUARDED at the use site — MUST be
        flagged, tagged as the `isFetching` (guard-aware) taint, proving
        guard-awareness is inherited from the property renamed FROM."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "demo", "pages/Panel.tsx", _GAP1_POSITIVE_RENAMED_ISFETCHING_UNGUARDED)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "renamed unguarded isFetching binding must be flagged"
        assert any("`isFetching`" in i["issue"] and "loadingWa" in i["issue"] for i in issues)
        assert not any("Shape 5" in i["issue"] for i in issues), "must not be mis-tagged as isLoading Shape 5"

    def test_gap1_negative_renamed_isfetching_guarded_not_flagged(self, tmp_path):
        """The SAME renamed `isFetching` local, guarded `&& !data` at the
        use site — MUST NOT be flagged. Proves guard resolution at the use
        site works for a renamed alias exactly as it does for the
        `const carregando = ...` VariableDeclaration alias case."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "demo", "pages/Panel.tsx", _GAP1_NEGATIVE_RENAMED_ISFETCHING_GUARDED)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"guarded renamed isFetching binding must not be flagged: {issues}"

    def test_gap1_negative_usestate_array_not_a_rename_not_flagged(self, tmp_path):
        """A `useState` ARRAY-destructured local — no `ObjectBindingPattern`
        property to rename FROM at all — MUST NOT be flagged. Proves the
        Gap-1 fix stays scoped to `ObjectBindingPattern` and does not
        regress the existing useState exclusion."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "erp-imobiliario", "components/AddRoleModal.tsx", _GAP1_NEGATIVE_USESTATE_ARRAY_NOT_A_RENAME)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"useState array-destructure must not be flagged: {issues}"

    # -----------------------------------------------------------------
    # Gap 2 — negation stops the climb.
    # -----------------------------------------------------------------

    def test_gap2_positive_negated_isloading_ternary_flagged(self, tmp_path):
        """The REAL `adconnect/pages/Orders.tsx` shape — `!isLoading &&
        rows.length === 0 ? <Empty/> : <List/>` — MUST be flagged. Confirmed
        FAILING against the pre-fix scanner (`[]`) before this fix landed.
        Bare destructured `isLoading` (no dot) — also invisible to Mode A's
        `_HANDROLLED_LOADING_GUARD_RE`, so this is a Mode-B-only gap."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "adconnect", "pages/Orders.tsx", _GAP2_POSITIVE_NEGATED_ISLOADING_TERNARY)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "negated isLoading reaching a JSX ternary must be flagged"
        assert any("Shape 5" in i["issue"] for i in issues)
        assert any("JSX ternary" in i["issue"] for i in issues)

    def test_gap2_negative_double_negation_guarded_not_flagged(self, tmp_path):
        """`!!isFetching && !data` — double negation round-trips to the
        ORIGINAL protectively-guarded shape — MUST NOT be flagged. Proves
        the `negated` tracker is a true XOR flip, not a one-shot latch."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "demo", "pages/Panel.tsx", _GAP2_NEGATIVE_DOUBLE_NEGATION_GUARDED)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues == [], f"double-negated guarded isFetching must not be flagged: {issues}"

    def test_gap2_positive_negated_isfetching_not_rescued_by_guard(self, tmp_path):
        """`!isFetching && !data` — a SINGLE negation of the guard-aware
        taint. Per the documented inverted-guard resolution, a `&&`-sibling
        match under negation must NEVER grant `guarded = true` — MUST be
        flagged, not silently trusted as safe."""
        repo = _make_repo(tmp_path)
        _product_file(repo, "demo", "pages/Panel.tsx", _GAP2_POSITIVE_NEGATED_ISFETCHING_NOT_RESCUED)
        issues = check_lying_loading_state(repo_root=repo)
        assert issues, "negated isFetching must not be silently rescued by an inverted guard match"
        assert any("`isFetching`" in i["issue"] for i in issues)
