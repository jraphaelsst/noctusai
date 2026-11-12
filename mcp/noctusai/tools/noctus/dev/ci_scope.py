"""The CI path classifier: which suites a diff selects. ONE source for `.github/workflows/test.yml` (`changes`
job) and the release steward's deliverable item 5.

WHY (2026-11-10). Item 5 judged a delivery by a fixed keeper set while CI picked suites from the diff, so three
deliveries went 5/5 and were ejected by the merge queue on suites the diff had selected (fleet-parametrized
compliance tests; seed + the toolkit tests a seed change breaks; a product's FE tests). The owner chose: item 5
runs what CI would run. Both sides must classify identically, so the classifier left the workflow's inline bash
and lives here; the workflow calls this file. Stdlib only - the `changes` job runs it with a bare `python3`.

Only the PATH classification moved. Choosing the diff BASE (the last heavy-green run, release refs that always run
full) stays in the workflow: it depends on the GitHub event, and item 5's base is always origin/dev.

CLI: `python3 ci_scope.py < changed-paths` prints the `$GITHUB_OUTPUT` lines
(run_heavy / harness_changed / shared_changed / changed_products).
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

#: a diff of ONLY these needs zero code verification
LEDGER_ONLY_RE = re.compile(r"^project-history/.*\.ndjson$")
#: the Claude Code mod surface (`harness-mod-tests`)
HARNESS_RE = re.compile(r"^(\.claude/mods/|\.claude-plugin/|\.claude/settings\.json$)")
#: a shared root invalidates every product (same family build-and-push.yml rebuilds the active set for);
#: active-scope.txt is in it so waking a product re-tests it at once
SHARED_RE = re.compile(r"^(seed/|requirements.*\.txt$|\.github/|scripts/ci/|package(-lock)?\.json$"
                       r"|deploy/fleet/active-scope\.txt$)")
PRODUCT_RE = re.compile(r"^products/([^/]+)/")


@dataclass(frozen=True)
class Scope:
    run_heavy: bool
    harness_changed: bool
    shared_changed: bool
    #: touched product slugs (empty when shared_changed: every product runs)
    changed_products: tuple[str, ...] = field(default_factory=tuple)

    def product_selected(self, slug: str) -> bool:
        return self.run_heavy and (self.shared_changed or slug in self.changed_products)

    def github_output(self) -> list[str]:
        b = lambda v: "true" if v else "false"  # noqa: E731
        return [f"run_heavy={b(self.run_heavy)}", f"harness_changed={b(self.harness_changed)}",
                f"shared_changed={b(self.shared_changed)}",
                "changed_products=," + "".join(f"{s}," for s in self.changed_products)]


#: what CI does with no usable diff base: everything
FULL = Scope(run_heavy=True, harness_changed=True, shared_changed=True)


def classify(changed: list[str]) -> Scope:
    paths = [p.strip() for p in changed if p.strip()]
    if not [p for p in paths if not LEDGER_ONLY_RE.match(p)]:
        return Scope(run_heavy=False, harness_changed=False, shared_changed=False)
    harness = any(HARNESS_RE.match(p) for p in paths)
    if any(SHARED_RE.match(p) for p in paths):
        return Scope(run_heavy=True, harness_changed=harness, shared_changed=True)
    slugs = sorted({m.group(1) for p in paths if (m := PRODUCT_RE.match(p))})
    return Scope(run_heavy=True, harness_changed=harness, shared_changed=False, changed_products=tuple(slugs))


def describe(scope: Scope) -> str:
    if not scope.run_heavy:
        return "scope: project-history/*.ndjson-only diff → every heavy job skipped"
    if scope.shared_changed:
        return "scope: shared root changed → every product matrix entry runs"
    return f"scope: product-scoped diff → changed products: {','.join(scope.changed_products) or 'none'}"


def main(argv: list[str] | None = None) -> int:
    scope = classify(sys.stdin.read().splitlines())
    print("\n".join(scope.github_output()))
    print(describe(scope), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
