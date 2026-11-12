"""Merge queue — ONE serialized, batched, CI-verified path into `dev` (2026-11-05).

Why (owner-ordered refinement after the 2026-11-04/05 julia-line integrate storm):
every `task_branch integrate` ran the full merged-tip gate set ON THE OWNER'S
LAPTOP, ~6 sessions shared 2 hardware slots, a single integrate waited 2h20m, and
each result went stale the moment a peer pushed (rebase -> re-run). Industry
practice (Bors "not rocket science rule", GitHub/GitLab merge trains, Uber
SubmitQueue) is a queue that tests each change against the state `dev` WILL have,
on CI runners, never on developer machines. GitHub's native merge queue is not
available to a user-owned repository, so this is a small Bors-shaped queue on
GitHub Actions. KB § PATTERNS/devops/merge-queue.md.

Shape
-----
* ENQUEUE (local, `task_branch action='enqueue'`): rebase onto origin/dev, the
  cheap local keepers (pre-push: doc-staleness, branch-tree, migration renumber),
  then push the branch to `refs/heads/mq/<slug>--<sha7>`. No local merged-tip
  gates — CI is the verdict.
* DRAIN (CI, `.github/workflows/merge-queue.yml`, concurrency-serialized): take
  the oldest `mq/*` entries (up to `batch_limit`), compose them onto `dev` in a
  scratch worktree (fast-forward / rebase / `--no-ff` merge for entries that
  carry merge commits), eject an entry that conflicts or adds a duplicate
  migration number, push the candidate to `mq-candidate/<run>-<n>`, dispatch the
  full `Tests & Build` on it, wait. Green -> fast-forward `dev` to the candidate
  (a ledger-only `project-history/**/*.ndjson` advance of dev meanwhile is
  rebased over without a re-test — the same predicate `test.yml` paths-ignore
  uses). Red -> retry the failed jobs once (flake guard), then halve the batch
  (bisection): a batch of one that is red is ejected with its failing jobs.
* PRIORITY LANE (2026-11-11): an entry whose diff touches `.github/` or whose tip
  carries an `MQ-Priority: <why>` trailer composes FIRST and ALONE, ahead of
  oldest-first and of an open bisection.
* PARALLEL WAVE (2026-11-11): up to `PARALLEL_CANDIDATES` product-disjoint
  groups (`products/<slug>/` only; anything else is the shared area and never
  runs alongside another) are composed on the same base and tested
  concurrently. The first green lands; a later green lands without a re-run
  only when its re-composed tree is the exact union of the two tested trees,
  otherwise it stays queued and is re-tested. KB merge-queue.md § 6c.
* VERDICT: a commit status `merge-queue` on the ENQUEUED sha (success = landed,
  description names the dev sha; failure = ejected + why). `task_branch
  action='landed'` reads it and runs the post-landing tail.

Stdlib only: this module runs on a bare CI runner with git + gh.
Invariant: `dev` only moves to a sha whose `Tests & Build` run is green (or a
ledger-only rebase of one). That is what makes "dev is green" true by
construction instead of by discipline.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# ONE path classifier with CI's `changes` job and release_steward item 5 (stdlib, same directory). As a package
# import under the toolkit / tests; as a sibling module when CI runs this file as a bare script.
if __package__:
    from . import ci_scope
else:  # pragma: no cover - the `python3 merge_queue.py drain` path on the runner
    import ci_scope

QUEUE_PREFIX = "mq/"
CANDIDATE_PREFIX = "mq-candidate/"
STATUS_CONTEXT = "merge-queue"
CI_WORKFLOW = "test.yml"
DEFAULT_BATCH = 4
LEDGER_ONLY_RE = re.compile(r"^project-history/.*\.ndjson$")
MIGRATION_RE = re.compile(r"^(?P<dir>(?:products/[^/]+|seed)/.*?migrations)/(?P<num>\d+)[_-][^/]*\.sql$")
# Path-scoped workflows that normally fire on a push to dev. A queue landing is a
# GITHUB_TOKEN push, which GitHub deliberately does not turn into workflow runs,
# so the queue dispatches them itself when the landed diff touches their paths.
POST_LAND_DISPATCH: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("agents-secc-ci.yml", ("products/agents/", "seed/docker/",
                            "scripts/infra/build-base-images.sh", ".github/workflows/agents-secc-ci.yml")),
)
# A queue ref is `mq/<slug>--<sha7>`; the slug is everything before the last `--`.
WORKFLOW_PREFIX = ".github/workflows/"
EXTRAHEADER_KEY = "http.https://github.com/.extraheader"  # actions/checkout's persisted github.token header
PUSH_TOKEN_ENV = "MQ_PUSH_TOKEN"  # fine-grained PAT (contents+workflows write); env secret of the dev-only `merge-queue` environment
# GitHub's wording when a token without the `workflows` permission pushes a new commit touching workflow files.
WORKFLOW_REJECT_RE = re.compile(r"without\s+`?workflows`?\s+permission", re.I)
WORKFLOW_REJECT_LINE_RE = re.compile(r"refusing to allow[^\n)]*", re.I)  # GitHub's own sentence, for the eject reason
ENTRY_RE = re.compile(r"^(?P<slug>.+)--(?P<short>[0-9a-f]{7,40})$")

# PRIORITY LANE (2026-11-11): an entry that fixes CI itself (diff under `.github/`) or whose tip commit carries an
# `MQ-Priority: <why>` trailer composes FIRST and ALONE, ahead of oldest-first order (the apt-mirror CI fix waited
# behind the queue and the first candidate went infra-red without it). The trailer is the flag: it rides the commit
# through enqueue's rebase untouched, so no enqueue-path change is needed.
PRIORITY_PATH_PREFIX = ".github/"
PRIORITY_TRAILER_RE = re.compile(r"^MQ-Priority:\s*\S", re.M)
# PARALLEL CANDIDATES: up to K product-disjoint candidates run CI at the same time (same dev base). Anything outside
# products/<slug>/ is the one SHARED area and conflicts with everything: it never runs alongside another candidate.
PARALLEL_CANDIDATES = 2
SHARED_AREA = "shared"
NON_PRODUCT_SLUGS = frozenset({"seed"})  # products/seed/ is the shared seed, not a product

# DERIVED files: committed by every slice after it regenerates them, so two parallel slices
# always conflict on them although neither edit is "real" (2026-11-07 run 42405063978 ejected
# seed-finance-service-only + sw-documentos-service-only on access-tiers FINDINGS/findings/metrics).
# At compose time a conflict whose files are ALL inside one registered set is resolved to the
# queue head's copy and the set's `regen` re-derives it from the merged tree; any other
# conflicting file keeps the ejection. ONE place, as data: add a set here, nothing else.
# KB § PATTERNS/devops/merge-queue.md (derived-ledger coupling).
DERIVED_SETS: tuple[dict[str, Any], ...] = (
    {"name": "access-tiers",
     "paths": ("project-history/access-tiers/FINDINGS.md",
               "project-history/access-tiers/findings.ndjson",
               "project-history/access-tiers/metrics.ndjson"),
     "regen": ("mcp/noctusai/cli.py", "--findings-ledger-reconcile", "access-tier", "--found-by", "merge-queue")},
)
REDERIVE_MAX_STOPS = 50  # a linear entry replays commit by commit; each can stop on the derived files


def derived_set_for(files: list[str]) -> dict[str, Any] | None:
    """The registered derived set that owns EVERY conflicted file (None: empty, mixed, or unregistered)."""
    files = [f.strip() for f in files if f.strip()]
    for ds in DERIVED_SETS:
        if files and all(f in ds["paths"] for f in files):
            return ds
    return None


Runner = Callable[..., "tuple[int, str, str]"]


def redact(text: str, token: str = "") -> str:
    """Strip the push token (explicit or from env) and any URL userinfo from text that may be surfaced."""
    tok = token or os.environ.get(PUSH_TOKEN_ENV, "").strip()
    if tok:
        text = text.replace(tok, "***")
    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", text or "")


def _default_run(cmd: list[str], cwd: str | None = None, check: bool = False) -> tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(redact(f"{' '.join(cmd)} -> {p.returncode}: {p.stderr.strip()[:500]}"))
    return p.returncode, p.stdout, p.stderr


@dataclass
class Entry:
    ref: str          # mq/<slug>--<sha7>
    sha: str          # the enqueued tip
    slug: str
    committed_at: int  # tip committer date (enqueue rebases, so ~= enqueue time)


@dataclass
class Outcome:
    landed: list[dict[str, Any]] = field(default_factory=list)
    ejected: list[dict[str, Any]] = field(default_factory=list)
    rounds: list[dict[str, Any]] = field(default_factory=list)


# ── pure helpers (unit-tested) ───────────────────────────────────────────────

def parse_entry(ref: str, sha: str, committed_at: int) -> Entry | None:
    name = ref[len(QUEUE_PREFIX):] if ref.startswith(QUEUE_PREFIX) else None
    if not name:
        return None
    m = ENTRY_RE.match(name)
    slug = m.group("slug") if m else name
    return Entry(ref=ref, sha=sha, slug=slug, committed_at=committed_at)


def order_entries(entries: list[Entry]) -> list[Entry]:
    """FIFO by enqueue time (tip committer date), ref name as the tiebreak."""
    return sorted(entries, key=lambda e: (e.committed_at, e.ref))


def is_priority(paths: list[str], message: str = "") -> bool:
    return any(p.startswith(PRIORITY_PATH_PREFIX) for p in paths) or bool(PRIORITY_TRAILER_RE.search(message or ""))


def entry_areas(paths: list[str]) -> frozenset[str]:
    """The areas an entry touches: one per products/<slug>/, SHARED_AREA for anything else (or no readable diff)."""
    areas = set()
    for p in paths:
        m = ci_scope.PRODUCT_RE.match(p)
        areas.add(m.group(1) if m and m.group(1) not in NON_PRODUCT_SLUGS else SHARED_AREA)
    return frozenset(areas or {SHARED_AREA})


def partition_wave(pool: list[Entry], paths_by_ref: dict[str, list[str]], limit: int,
                   k: int = PARALLEL_CANDIDATES) -> list[list[Entry]]:
    """Groups of area-disjoint entries that may run as concurrent candidates; [] = no wave (the caller runs ONE batch).
    Only the leading non-shared prefix of the next `limit` entries is eligible (FIFO: a shared entry waits for its turn
    and never overlaps another candidate); entries that share a product merge into one group; at most `k` groups."""
    if k < 2:
        return []
    prefix: list[Entry] = []
    for e in pool[:limit]:
        if SHARED_AREA in entry_areas(paths_by_ref.get(e.ref, [])):
            break
        prefix.append(e)
    groups: list[tuple[set[str], list[Entry]]] = []
    for e in prefix:
        areas, members = set(entry_areas(paths_by_ref[e.ref])), [e]
        for g in [g for g in groups if g[0] & areas]:
            groups.remove(g)
            areas |= g[0]
            members = g[1] + members
        groups.append((areas, members))
    groups.sort(key=lambda g: prefix.index(g[1][0]))
    return [g[1] for g in groups[:k]] if len(groups) >= 2 else []


def is_ledger_only(paths: list[str]) -> bool:
    paths = [p for p in paths if p.strip()]
    return bool(paths) and all(LEDGER_ONLY_RE.match(p) for p in paths)


def migration_numbers(paths: list[str]) -> dict[tuple[str, str], list[str]]:
    """{(migrations_dir, number-as-int-string): [files]} for every migration path."""
    out: dict[tuple[str, str], list[str]] = {}
    for p in paths:
        m = MIGRATION_RE.match(p.strip())
        if m:
            out.setdefault((m.group("dir"), str(int(m.group("num")))), []).append(p.strip())
    return out


def new_migration_collisions(before: list[str], after: list[str]) -> list[dict[str, Any]]:
    """Duplicate migration numbers present in `after` but not already in `before`
    (pre-existing duplicates, e.g. SW 005, are history — never this entry's fault)."""
    old = {k for k, v in migration_numbers(before).items() if len(v) > 1}
    return [{"dir": d, "number": n, "files": sorted(files)}
            for (d, n), files in sorted(migration_numbers(after).items())
            if len(files) > 1 and (d, n) not in old]


def next_batch_limit(current: int, batch_size: int, green: bool, default: int = DEFAULT_BATCH) -> int:
    """Bisection: a red batch of N>1 retries with its first half; green resets."""
    if green:
        return default
    return max(1, (batch_size + 1) // 2) if batch_size > 1 else 1


def post_land_workflows(paths: list[str]) -> list[str]:
    return [wf for wf, prefixes in POST_LAND_DISPATCH
            if any(p.startswith(prefixes) for p in paths)]


def touches_workflows(paths: list[str]) -> bool:
    return any(p.strip().startswith(WORKFLOW_PREFIX) for p in paths)


def is_workflow_rejection(stderr: str) -> bool:
    return bool(WORKFLOW_REJECT_RE.search(stderr or ""))


def push_token_from_env(env: dict[str, str] | None = None) -> str:
    """The seam: a PAT with the `workflows` permission (env secret MQ_PUSH_TOKEN of the `merge-queue` environment)."""
    return (env if env is not None else os.environ).get(PUSH_TOKEN_ENV, "").strip()


WORKFLOW_EJECT_WHY = ("changes .github/workflows/* - the queue's token cannot push workflow edits; "
                      "land via the steward's workflow-file path")


def _flush_print(msg: str) -> None:
    """The drain's default log. Flushed per line: stdout is a pipe on the runner (block-buffered), and a
    cancelled drain (2026-11-11, run 43060568244) lost EVERY line it had printed - including the push
    rejection that would have named the cause."""
    print(msg, flush=True)


def status_description(text: str) -> str:
    return text if len(text) <= 140 else text[:137] + "..."


# ── culprit attribution (2026-11-11) ─────────────────────────────────────────
# A red batch used to be binary-bisected, ~50 min of CI per step. Most reds name the failing
# test, and the test's area (product / seed / mcp toolkit / migration replay) says which
# entry's diff could have caused it. When EXACTLY ONE entry covers the failure it is ejected
# directly; zero / several / unreadable falls back to the bisect, with the reason logged.
FAILED_TEST_RE = re.compile(r"\b(?:FAILED|ERROR)\s+(?P<path>[\w./-]+\.py)(?P<rest>::\S+)?")
JOB_PRODUCT_RE = re.compile(r"\(([a-z0-9][a-z0-9-]*)\)\s*$")
MIGRATION_PATH_RE = re.compile(r"^(?:products/(?P<p>[^/]+)|seed)/.*?migrations/[^/]+\.sql$")
# Failures whose cause is a MIGRATION an entry added (the replay + live-guard probes).
MIGRATION_TEST_RE = re.compile(r"verify_db_guards|_on_replay|migration_replay", re.I)


def failed_test_ids(log_text: str) -> list[str]:
    """`path::Class::test` ids from a pytest `-rf`/`-rfE` summary inside `gh run view --log-failed`."""
    seen: list[str] = []
    for m in FAILED_TEST_RE.finditer(log_text or ""):
        tid = m.group("path") + (m.group("rest") or "")
        if tid not in seen:
            seen.append(tid)
    return seen


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _breaks_product(slug: str) -> Callable[[str], bool]:
    """A change to `path` can break product `slug`'s tests iff CI would select that product's suites for it
    (`ci_scope`: its own products/<slug>/ or any shared root - seed/, requirements, .github/, scripts/ci/, ...)."""
    return lambda path: ci_scope.classify([path]).product_selected(slug)


def _breaks_shared(path: str) -> bool:
    return bool(ci_scope.SHARED_RE.match(path))


def _breaks_toolkit(path: str) -> bool:
    return path.startswith("mcp/") or _breaks_shared(path)


def failure_areas(test_ids: list[str], failed_jobs: list[str], known_products: list[str],
                  ) -> list[dict[str, Any]]:
    """Each failure -> {name, touches, migrations_of}: `touches(path)` says whether a change to that path can break it,
    classified by `ci_scope` (the classifier CI's `changes` job and item 5 use - one answer, 2026-11-12).
    `migrations_of` set (a product slug or "*") = only an entry ADDING a migration (of that product) matches.
    Wider is the safe direction: two matching entries fall back to bisect; a too-narrow area ejects an innocent."""
    areas: list[dict[str, Any]] = []
    for tid in test_ids:
        path = tid.split("::", 1)[0]
        m = ci_scope.PRODUCT_RE.match(path)
        if MIGRATION_TEST_RE.search(tid):
            named = [p for p in known_products if len(p) > 2 and _norm(p) in _norm(tid.split("::", 1)[-1])]
            areas.append({"name": tid, "touches": None, "migrations_of": named[0] if len(named) == 1 else "*"})
        elif m and m.group(1) not in NON_PRODUCT_SLUGS:
            areas.append({"name": tid, "touches": _breaks_product(m.group(1)), "migrations_of": None})
        elif m or path.startswith("seed/") or path.startswith("templates/product-seed/"):
            areas.append({"name": tid, "touches": _breaks_shared, "migrations_of": None})
        elif path.startswith("mcp/"):
            areas.append({"name": tid, "touches": _breaks_toolkit, "migrations_of": None})
    if areas:
        return areas
    for job in failed_jobs:  # no readable test id: only a job whose scope is unambiguous counts
        pm = JOB_PRODUCT_RE.search(job)
        if job.startswith("Product Backend Tests") and pm and pm.group(1) in known_products:
            areas.append({"name": job, "touches": _breaks_product(pm.group(1)), "migrations_of": None})
        elif job.startswith("Seed "):
            areas.append({"name": job, "touches": _breaks_shared, "migrations_of": None})
        elif job.startswith("MCP Toolkit Tests"):
            areas.append({"name": job, "touches": _breaks_toolkit, "migrations_of": None})
    return areas


def attribute_culprit(test_ids: list[str], failed_jobs: list[str],
                      entry_paths: dict[str, list[str]]) -> tuple[str | None, str]:
    """(culprit_ref, why). culprit_ref is None - with the reason the caller logs - unless EXACTLY ONE entry's
    diff touches the failing areas. Pure: never guesses; every None is a documented fallback to bisect."""
    known = sorted({m.group(1) for ps in entry_paths.values() for p in ps if (m := ci_scope.PRODUCT_RE.match(p))})
    areas = failure_areas(test_ids, failed_jobs, known)
    if not areas:
        return None, f"failure unreadable (no test id or scoped job in {failed_jobs[:3] or 'the log'})"
    hits: dict[str, str] = {}
    for ref, paths in entry_paths.items():
        for a in areas:
            mig = a["migrations_of"]
            if mig is not None:
                match = next((p for p in paths if (m := MIGRATION_PATH_RE.match(p))
                              and (mig == "*" or m.group("p") == mig)), None)
            else:
                match = next((p for p in paths if a["touches"](p)), None)
            if match:
                hits[ref] = f"{a['name']} <- {match}"
                break
    if len(hits) == 1:
        ref, why = next(iter(hits.items()))
        return ref, why
    return None, (f"{len(hits)} entries match the failing areas" if hits else
                  "no entry touches the failing areas")


# ── the queue against a real git/gh ──────────────────────────────────────────

class Queue:
    def __init__(self, repo: str, remote: str = "origin", dev: str = "dev",
                 run: Runner = _default_run, run_url: str = "", run_id: str = "local",
                 poll_s: int = 60, timeout_s: int = 5400, sleep: Callable[[float], None] = time.sleep,
                 workdir: str | None = None, log: Callable[[str], None] = _flush_print,
                 workflow_token: bool | None = None, push_token: str | None = None,
                 regen: Callable[[str], tuple[bool, str]] | None = None,
                 derived_regen: Callable[[str, dict[str, Any]], tuple[bool, str]] | None = None,
                 merge_loss: Callable[[str, str], str] | None = None):
        self.repo, self.remote, self.dev = repo, remote, dev
        self.merge_loss = merge_loss or self._merge_loss_shadow
        self.regen = regen or self._regen_kb_counts
        self.derived_regen = derived_regen or self._regen_derived
        self.run, self.run_url, self.run_id = run, run_url, run_id
        self.poll_s, self.timeout_s, self.sleep = poll_s, timeout_s, sleep
        self.workdir = workdir or os.getcwd()
        self.log = log
        self.push_token = push_token_from_env() if push_token is None else push_token.strip()
        # workflow-capable = a token is configured; the bool override exists for tests (no real token needed).
        self.workflow_token = bool(self.push_token) if workflow_token is None else workflow_token

    def _redact(self, text: str) -> str:
        return redact(text, self.push_token)

    def push_remote(self, workflow_batch: bool) -> str:
        """Plain remote normally; the authenticated URL ONLY for a batch that needs the `workflows` permission
        (a PAT push triggers push workflows, a github.token push does not - never double-run CI)."""
        if workflow_batch and self.push_token and self.repo:
            return f"https://x-access-token:{self.push_token}@github.com/{self.repo}.git"
        return self.remote

    def push_cmd(self, remote: str, refspec: str) -> list[str]:
        """The git push argv. A push to the authenticated PAT URL first CLEARS the checkout's persisted
        `http.https://github.com/.extraheader` (actions/checkout writes `AUTHORIZATION: basic <github.token>`
        there, and git sends it on EVERY github.com URL - including `x-access-token:<PAT>@github.com`). Left in
        place, a "PAT" push can authenticate as github.token, which has no `workflows` permission (b5's
        hypothesis, 2026-11-11; the eject reason now quotes GitHub's own sentence, which says whether the
        refused actor was a "GitHub App" or a "Personal Access Token"). The plain remote keeps the header:
        that is its only credential."""
        if remote != self.remote and remote.startswith("https://x-access-token:"):
            return ["git", "-c", f"{EXTRAHEADER_KEY}=", "push", remote, refspec]
        return ["git", "push", remote, refspec]

    def batch_needs_workflows(self, base: str, sha: str) -> bool:
        return bool(self.push_token) and touches_workflows(self.changed_paths(base, sha))

    # git plumbing ------------------------------------------------------------
    def git(self, *args: str, cwd: str | None = None, check: bool = True) -> str:
        rc, out, err = self.run(["git", *args], cwd=cwd or self.workdir)
        if check and rc != 0:
            raise RuntimeError(self._redact(f"git {' '.join(args)} failed ({rc}): {err.strip()[:400]}"))
        return out.strip()

    def _regen_kb_counts(self, wt: str) -> tuple[bool, str]:
        """Deterministic re-derivation of the kb-counts blocks in the drain worktree."""
        cli = os.path.join(wt, "mcp", "noctusai", "cli.py")
        rc, out, err = self.run([sys.executable, cli, "--update-kb-counts", "--worktree-path", wt], cwd=wt)
        return rc == 0, (err or out).strip()[-400:]

    def _regen_derived(self, wt: str, ds: dict[str, Any]) -> tuple[bool, str]:
        """Re-derive one registered derived set from the composed tree (argv is data in DERIVED_SETS)."""
        script, *rest = ds["regen"]
        rc, out, err = self.run([sys.executable, os.path.join(wt, script), *rest], cwd=wt)
        return rc == 0, (err or out).strip()[-400:]

    def _merge_loss_shadow(self, wt: str, merge_sha: str) -> str:
        """SHADOW merge-loss detector on one composed merge commit (noctus.dev.merge_loss_check):
        returns a one-line verdict for the drain log. NEVER ejects an entry and never raises -
        promotion to blocking is gated on measured false-alarm data (KB § PATTERNS/common/
        auto-generated-merge-drivers.md § Merge-loss detector). `--no-log`: the runner is ephemeral,
        so the finding lives in this drain log (grep `[merge-loss]`)."""
        cli = os.path.join(wt, "mcp", "noctusai", "cli.py")
        if not os.path.exists(cli):
            return "merge-loss: skipped (no cli.py in the composed tree)"
        try:
            rc, out, err = self.run([sys.executable, cli, "--check-merge-loss", "--no-log",
                                     "--merge-sha", merge_sha, "--worktree-path", wt], cwd=wt)
            j = json.loads(out[out.index("{\n"):])
        except (ValueError, OSError) as exc:
            return f"merge-loss: UNMEASURABLE (not a pass): {exc}"
        if j.get("verdict") == "dropped":
            lines = "; ".join(f"{d['side']}:{d['path']}: {d['line'][:60]!r}" for d in j.get("dropped", [])[:5])
            return f"merge-loss: SHADOW DROPPED {j.get('dropped_count')} line(s) in {merge_sha[:9]} - {lines}"
        return f"merge-loss: {j.get('verdict')} ({j.get('checked_files')} file(s))"

    def _unmerged(self, wt: str) -> list[str]:
        return self.git("diff", "--name-only", "--diff-filter=U", cwd=wt, check=False).split()

    def _resolve_to_head(self, wt: str, files: list[str]) -> bool:
        """Take the queue head's copy of derived conflicted files and stage them."""
        for args in (["checkout", "--ours", "--", *files], ["add", "--", *files]):
            if self.run(["git", *args], cwd=wt)[0] != 0:
                return False
        return True

    def rederive_conflict(self, e: Entry, wt: str, kind: str) -> tuple[dict[str, Any] | None, list[str]]:
        """A merge/rebase of `e` just stopped on conflicts. If every conflicted file belongs to ONE
        registered derived set, resolve it to the head's copy and finish the operation; the set is
        re-derived by `finish_rederive` once the entry is fully applied. Returns (set, files) or
        (None, files) when the conflict is real (caller aborts + ejects, exactly as before)."""
        seen: list[str] = []
        owner: dict[str, Any] | None = None
        for _ in range(REDERIVE_MAX_STOPS):
            files = self._unmerged(wt)
            if (kind == "rebase" and not files and owner is not None
                    and self.run(["git", "diff", "--cached", "--quiet"], cwd=wt)[0] == 0):
                # The commit touched ONLY derived files: resolved to head it is empty, so
                # `rebase --continue` stopped with nothing to commit. Drop it and keep going.
                if self.run(["git", "rebase", "--skip"], cwd=wt)[0] == 0:
                    return owner, seen
                continue
            ds = derived_set_for(files)
            if ds is None or (owner is not None and ds is not owner) or not self._resolve_to_head(wt, files):
                return None, seen + files
            owner, seen = ds, seen + files
            cont = (["git", "commit", "--no-edit"] if kind == "merge"
                    else ["git", "-c", "core.editor=true", "rebase", "--continue"])
            if self.run(cont, cwd=wt)[0] == 0:
                return owner, seen
            if kind == "merge":
                return None, seen
        return None, seen

    def finish_rederive(self, e: Entry, wt: str, ds: dict[str, Any], files: list[str]) -> tuple[bool, str]:
        ok, why = self.derived_regen(wt, ds)
        if not ok:
            return False, f"derived re-derivation of {ds['name']} failed: {why}"
        rc, porcelain, err = self.run(["git", "status", "--porcelain", "-z", "--untracked-files=all", "--",
                                       *ds["paths"]], cwd=wt)
        if rc != 0:
            return False, f"derived status read failed ({rc}): {err.strip()[:300]}"
        paths = [x[3:] for x in porcelain.split("\0") if len(x) > 3]
        if paths:
            for args in (["add", "--", *paths],
                         ["commit", "-q", "-m", f"chore({ds['name']}): re-derive conflicted ledger at compose [auto]",
                          "--", *paths]):
                rc, _o, err = self.run(["git", *args], cwd=wt)
                if rc != 0:
                    return False, self._redact(f"derived commit failed: git {args[0]} ({rc}): {err.strip()[:300]}")
        # Telemetry: one line per re-derive in the drain's CI log (grep `mq-derived-regen`).
        self.log(f"[mq-derived-regen] set={ds['name']} slug={e.slug} conflicted={sorted(set(files))} "
                 f"rederived={len(paths)} run={self.run_id}")
        return True, ""

    def regen_and_commit_counts(self, wt: str) -> tuple[bool, str]:
        """Merge drivers re-derive counts against the PRE-merge working tree
        (ort runs them before checkout), so the composed block can be stale and
        the batch goes red on the kb-counts drift check. Re-derive on the
        composed head and commit ONLY derived paths. Returns (ok, reason)."""
        ok, why = self.regen(wt)
        if not ok:
            return False, f"kb-counts regeneration failed: {why}"
        # RAW read (never self.git: it strips, eating the leading ' ' of a ' M <path>'
        # first entry so [3:] cut 'KNOWLEDGE-BASE' to 'NOWLEDGE-BASE' — 2026-11-06 wedge).
        # -z: NUL-separated, paths unquoted; each entry is 'XY <path>'.
        rc, porcelain, err = self.run(["git", "status", "--porcelain", "-z", "--untracked-files=all", "--",
                                       "KNOWLEDGE-BASE/", "CLAUDE.md"], cwd=wt)
        if rc != 0:
            return False, f"kb-counts status read failed ({rc}): {err.strip()[:300]}"
        paths = [e[3:] for e in porcelain.split("\0") if len(e) > 3]
        if not paths:
            return True, ""
        # A failure here ejects the entry with the reason; it never crashes the drain
        # (a crash wedges EVERY queued entry, not just this one).
        for args in (["add", "--", *paths],
                     ["commit", "-q", "-m", "chore(kb-counts): regenerate derived counts at compose [auto]",
                      "--", *paths]):
            rc, _out, err = self.run(["git", *args], cwd=wt)
            if rc != 0:
                return False, self._redact(f"kb-counts commit failed: git {args[0]} ({rc}): {err.strip()[:300]}")
        self.log(f"  regenerated kb-counts at compose ({len(paths)} file(s))")
        return True, ""

    def fetch(self) -> None:
        self.git("fetch", "--prune", self.remote,
                 f"+refs/heads/{self.dev}:refs/remotes/{self.remote}/{self.dev}",
                 f"+refs/heads/{QUEUE_PREFIX}*:refs/remotes/{self.remote}/{QUEUE_PREFIX}*")

    def dev_sha(self) -> str:
        return self.git("rev-parse", f"refs/remotes/{self.remote}/{self.dev}")

    def entries(self) -> list[Entry]:
        out = self.git("for-each-ref", "--format=%(refname)%09%(objectname)%09%(committerdate:unix)",
                       f"refs/remotes/{self.remote}/{QUEUE_PREFIX}")
        found = []
        for line in out.splitlines():
            ref, sha, ts = line.split("\t")
            short = ref[len(f"refs/remotes/{self.remote}/"):]
            e = parse_entry(short, sha, int(ts or 0))
            if e:
                found.append(e)
        return order_entries(found)

    def changed_paths(self, a: str, b: str) -> list[str]:
        return [p for p in self.git("diff", "--name-only", a, b).splitlines() if p.strip()]

    def tree_paths(self, sha: str) -> list[str]:
        return self.git("ls-tree", "-r", "--name-only", sha).splitlines()

    # github plumbing ---------------------------------------------------------
    def gh(self, *args: str, check: bool = True) -> str:
        rc, out, err = self.run(["gh", *args], cwd=self.workdir)
        if check and rc != 0:
            raise RuntimeError(self._redact(f"gh {' '.join(args)} failed ({rc}): {err.strip()[:400]}"))
        return out.strip()

    def set_status(self, sha: str, state: str, description: str) -> None:
        args = ["api", "-X", "POST", f"repos/{self.repo}/statuses/{sha}",
                "-f", f"state={state}", "-f", f"context={STATUS_CONTEXT}",
                "-f", f"description={status_description(description)}"]
        if self.run_url:
            args += ["-f", f"target_url={self.run_url}"]
        self.gh(*args, check=False)

    def delete_ref(self, ref: str) -> None:
        self.git("push", self.remote, f":refs/heads/{ref}", check=False)

    # lanes -------------------------------------------------------------------
    def entry_paths(self, base: str, e: Entry) -> list[str]:
        """What the entry itself changes (merge-base diff, so a branch that is behind dev is not charged with dev's
        newer commits). Unreadable -> [] which every caller treats as the conservative SHARED answer."""
        try:
            return [p for p in self.git("diff", "--name-only", f"{base}...{e.sha}").splitlines() if p.strip()]
        except RuntimeError:
            return []

    def priority_entry(self, pool: list[Entry], base: str) -> Entry | None:
        for e in pool:
            msg = self.git("log", "-1", "--format=%B", e.sha, check=False)
            if is_priority(self.entry_paths(base, e), msg):
                return e
        return None

    def plan_wave(self, pool: list[Entry], base: str, limit: int, k: int = PARALLEL_CANDIDATES) -> list[list[Entry]]:
        paths = {e.ref: self.entry_paths(base, e) for e in pool[:limit]}
        return partition_wave(pool, paths, limit, k)

    # compose -----------------------------------------------------------------
    def compose(self, batch: list[Entry], base: str, wt: str) -> tuple[str, list[Entry], list[dict]]:
        """Apply each entry onto `base` in a scratch worktree. Returns
        (candidate_sha, applied_entries, ejections)."""
        self.git("worktree", "add", "--detach", wt, base)
        applied: list[Entry] = []
        ejected: list[dict] = []
        head = base
        for e in batch:
            before_tree = self.tree_paths(head)
            merges = self.git("rev-list", "--merges", f"{head}..{e.sha}", cwd=wt)
            rc_anc, _, _ = self.run(["git", "merge-base", "--is-ancestor", head, e.sha], cwd=wt)
            how = ""
            rederive: tuple[dict[str, Any], list[str]] | None = None
            if rc_anc == 0:
                self.git("merge", "--ff-only", "--quiet", e.sha, cwd=wt)
                how = "fast-forward"
            elif merges:
                rc, out, err = self.run(["git", "merge", "--no-ff", "--no-edit", "-m",
                                         f"mq: merge {e.slug}", e.sha], cwd=wt)
                how = "merge"
                if rc != 0:
                    ds, rfiles = self.rederive_conflict(e, wt, "merge")
                    if ds is not None:
                        rederive = (ds, rfiles)
                    else:
                        files = " ".join(rfiles)
                        self.run(["git", "merge", "--abort"], cwd=wt)
                        ejected.append(self._eject_info(e, "conflict", f"conflicts with dev+queue ahead of it: {files.split()[:6]}"))
                        continue
            else:
                # Linear entry: replay its own commits (merge-base..tip) onto head.
                mb = self.git("merge-base", head, e.sha, cwd=wt)
                self.git("checkout", "--quiet", "--detach", e.sha, cwd=wt)
                rc, out, err = self.run(["git", "rebase", "--quiet", "--onto", head, mb], cwd=wt)
                how = "rebase"
                if rc != 0:
                    ds, rfiles = self.rederive_conflict(e, wt, "rebase")
                    if ds is not None:
                        rederive = (ds, rfiles)
                    else:
                        files = " ".join(rfiles)
                        self.run(["git", "rebase", "--abort"], cwd=wt)
                        self.git("checkout", "--quiet", "--detach", head, cwd=wt)
                        ejected.append(self._eject_info(e, "conflict", f"conflicts with dev+queue ahead of it: {files.split()[:6]}"))
                        continue
            if rederive is not None:
                ok, why = self.finish_rederive(e, wt, *rederive)
                if not ok:
                    self.run(["git", "reset", "--hard", "--quiet", head], cwd=wt)
                    self.git("checkout", "--quiet", "--detach", head, cwd=wt)
                    ejected.append(self._eject_info(e, "derived_regen", why))
                    continue
            if how == "merge":
                try:
                    self.log("  [merge-loss] " + self.merge_loss(wt, self.git("rev-parse", "HEAD", cwd=wt)))
                except RuntimeError as exc:  # shadow: a broken detector must never eject an entry
                    self.log(f"  [merge-loss] UNMEASURABLE (not a pass): {exc}")
            ok, why = self.regen_and_commit_counts(wt)
            if not ok:
                self.run(["git", "reset", "--hard", "--quiet", head], cwd=wt)
                self.git("checkout", "--quiet", "--detach", head, cwd=wt)
                ejected.append(self._eject_info(e, "kb_counts_regen", why))
                continue
            new_head = self.git("rev-parse", "HEAD", cwd=wt)
            collisions = new_migration_collisions(before_tree, self.tree_paths(new_head))
            if collisions:
                self.git("checkout", "--quiet", "--detach", head, cwd=wt)
                c = collisions[0]
                ejected.append(self._eject_info(
                    e, "migration_collision",
                    f"migration number {c['number']} in {c['dir']} already taken: {c['files']} - renumber and re-enqueue"))
                continue
            if not self.workflow_token and new_head != e.sha and touches_workflows(self.changed_paths(head, new_head)):
                # A NEW commit object (rebase/merge) changing a workflow file is unpushable with github.token.
                self.git("reset", "--hard", "--quiet", head, cwd=wt)
                ejected.append(self._eject_info(e, "needs_workflow_token", WORKFLOW_EJECT_WHY))
                continue
            head = new_head
            applied.append(e)
            self.log(f"  composed {e.slug} ({how}) -> {head[:9]}")
        return head, applied, ejected

    def _eject_info(self, e: Entry, kind: str, why: str) -> dict[str, Any]:
        return {"slug": e.slug, "ref": e.ref, "sha": e.sha, "kind": kind, "why": why}

    # CI ----------------------------------------------------------------------
    def dispatch_and_wait(self, cand_ref: str, cand_sha: str, base: str = "") -> dict[str, Any]:
        # `base` = the dev sha the candidate was composed on (2026-11-05). A
        # dispatched run has no `event.before`, so test.yml's range keepers
        # fell back to `SHA~50..SHA` and judged 50 commits that were already
        # on dev; with base they judge exactly what this batch adds.
        self.gh("workflow", "run", CI_WORKFLOW, "--ref", cand_ref, "-R", self.repo,
                *(("-f", f"base={base}") if base else ()))
        run_id = None
        deadline = time.time() + self.timeout_s
        for _ in range(30):
            self.sleep(10)
            out = self.gh("run", "list", "-R", self.repo, "--workflow", CI_WORKFLOW, "--branch", cand_ref,
                          "--event", "workflow_dispatch", "--limit", "5", "--json", "databaseId,headSha", check=False)
            runs = [r for r in json.loads(out or "[]") if r.get("headSha") == cand_sha]
            if runs:
                run_id = str(runs[0]["databaseId"])
                break
        if not run_id:
            return {"verdict": "unavailable", "detail": "dispatched run never appeared"}
        return self.wait_run(run_id, deadline, retried=False)

    def wait_run(self, run_id: str, deadline: float, retried: bool) -> dict[str, Any]:
        while time.time() < deadline:
            out = self.gh("run", "view", run_id, "-R", self.repo, "--json", "status,conclusion,url,jobs", check=False)
            try:
                info = json.loads(out or "{}")
            except json.JSONDecodeError:
                info = {}
            if info.get("status") == "completed":
                failed = [j["name"] for j in info.get("jobs", [])
                          if j.get("conclusion") not in ("success", "skipped", None)]
                if info.get("conclusion") == "success":
                    return {"verdict": "green", "run_id": run_id, "url": info.get("url")}
                if not retried and failed:
                    self.log(f"  run {run_id} red on {failed} - re-running failed jobs once (flake guard)")
                    self.gh("run", "rerun", run_id, "--failed", "-R", self.repo, check=False)
                    self.sleep(20)
                    return self.wait_run(run_id, deadline, retried=True)
                return {"verdict": "red", "run_id": run_id, "url": info.get("url"), "failed_jobs": failed}
            self.sleep(self.poll_s)
        return {"verdict": "timeout", "run_id": run_id}

    def red_attribution(self, ci: dict[str, Any], applied: list[Entry], base: str) -> tuple[Entry | None, str]:
        """Read the red run's failing tests and try to name the one entry that caused it (see attribute_culprit)."""
        try:
            log = self.gh("run", "view", str(ci.get("run_id", "")), "-R", self.repo, "--log-failed", check=False)
            paths = {e.ref: self.changed_paths(base, e.sha) for e in applied}
        except RuntimeError as exc:
            return None, f"failure unreadable ({exc})"
        ref, why = attribute_culprit(failed_test_ids(log), list(ci.get("failed_jobs", [])), paths)
        return next((e for e in applied if e.ref == ref), None), why

    # land --------------------------------------------------------------------
    def land(self, cand_sha: str, tested_base: str, wt: str) -> tuple[bool, str]:
        """FF dev to the candidate. Returns (landed, sha_on_dev)."""
        for _ in range(5):
            remote = self.push_remote(self.batch_needs_workflows(tested_base, cand_sha))
            rc, _, err = self.run(self.push_cmd(remote, f"{cand_sha}:refs/heads/{self.dev}"), cwd=wt)
            if rc == 0:
                return True, cand_sha
            self.fetch()
            now = self.dev_sha()
            moved = self.changed_paths(tested_base, now)
            if not is_ledger_only(moved):
                self.log(f"  dev moved with code ({len(moved)} paths) since the test base - re-test needed")
                return False, ""
            # ledger-only advance: replay the candidate over it, no re-test (test.yml paths-ignore).
            self.git("checkout", "--quiet", "--detach", cand_sha, cwd=wt)
            rc, _, err = self.run(["git", "rebase", "--quiet", "--onto", now, tested_base], cwd=wt)
            if rc != 0:
                self.run(["git", "rebase", "--abort"], cwd=wt)
                return False, ""
            cand_sha, tested_base = self.git("rev-parse", "HEAD", cwd=wt), now
        return False, ""

    # drain -------------------------------------------------------------------
    def drain(self, batch_limit: int = DEFAULT_BATCH, max_rounds: int = 12, dry_run: bool = False) -> Outcome:
        res = Outcome()
        limit = batch_limit
        # Bisection state: the refs of a red batch not yet proven clean. While any remain queued, batches
        # are drawn ONLY from them -- a green half must not reset to a full batch, or the untested half
        # (holding the culprit) is re-composed with fresh entries and turns their batch red too
        # (2026-11-05: red -6, green -7, then -8 = culprit + 3 innocent entries).
        suspects: list[str] = []
        for n in range(1, max_rounds + 1):
            self.fetch()
            queue = self.entries()
            if not queue:
                self.log("queue empty")
                break
            suspects = [r for r in suspects if any(e.ref == r for e in queue)]
            pool = [e for e in queue if e.ref in suspects] if suspects else queue
            base = self.dev_sha()
            prio = self.priority_entry(queue, base)  # the priority lane outranks FIFO AND an open bisection
            groups: list[list[Entry]] = []
            if prio is not None:
                batch = [prio]
            else:
                batch = pool[:limit]
                groups = [] if suspects else self.plan_wave(pool, base, limit)
            lane = "priority" if prio is not None else f"parallel x{len(groups)}" if groups else "batch"
            self.log(f"round {n} [{lane}]: dev={base[:9]} batch={[e.slug for e in batch] if not groups else [[e.slug for e in g] for g in groups]} (queue {len(queue)})")
            if dry_run:
                res.rounds.append({"round": n, "batch": [e.slug for e in batch], "lane": lane, "dry_run": True})
                break
            if groups:
                suspects, limit, stop = self._run_wave(n, groups, base, res, batch_limit, limit)
                if stop:
                    break
                continue
            saved = (list(suspects), limit) if prio is not None else None  # a priority run never moves the bisection
            wt = tempfile.mkdtemp(prefix="mq-")
            os.rmdir(wt)
            try:
                cand, applied, ejected = self.compose(batch, base, wt)
                for x in ejected:
                    self._finish_eject(x)
                    res.ejected.append(x)
                if not applied:
                    continue
                if cand == base:
                    # Everything was already on dev (re-enqueued landed work).
                    for e in applied:
                        self._finish_land(e, base)
                        res.landed.append({"slug": e.slug, "dev": base})
                    continue
                cand_ref = f"{CANDIDATE_PREFIX}{self.run_id}-{n}"
                remote = self.push_remote(self.batch_needs_workflows(base, cand))
                rc, _, perr = self.run(self.push_cmd(remote, f"{cand}:refs/heads/{cand_ref}"), cwd=self.workdir)
                if rc != 0:
                    # Never crash the drain on a rejected push (2026-11-05: it wedged the queue ~1.5h).
                    if self._handle_push_rejection(applied, base, perr, res, via_pat=remote != self.remote):
                        suspects = [e.ref for e in applied
                                    if not any(x["ref"] == e.ref for x in res.ejected)]
                        limit = next_batch_limit(limit, len(applied), green=False) if suspects else batch_limit
                    continue
                for e in applied:
                    self.set_status(e.sha, "pending", f"testing in batch {cand_ref} ({len(applied)} entr{'y' if len(applied) == 1 else 'ies'})")
                ci = self.dispatch_and_wait(cand_ref, cand, base)
                rnd = {"round": n, "candidate": cand, "batch": [e.slug for e in applied], "ci": ci}
                if ci["verdict"] == "green":
                    ok, landed_sha = self.land(cand, base, wt)
                    rnd["landed"] = ok
                    if ok:
                        for e in applied:
                            self._finish_land(e, landed_sha)
                            res.landed.append({"slug": e.slug, "dev": landed_sha})
                        for wf in post_land_workflows(self.changed_paths(base, landed_sha)):
                            self.gh("workflow", "run", wf, "--ref", self.dev, "-R", self.repo, check=False)
                            rnd.setdefault("dispatched", []).append(wf)
                    cleared = {e.ref for e in applied}
                    suspects = [r for r in suspects if r not in cleared]
                    # The culprit is in what is left: test the rest of the suspects (alone), else reset.
                    limit = len(suspects) if suspects else batch_limit
                elif ci["verdict"] == "red" and len(applied) == 1:
                    e = applied[0]
                    x = self._eject_info(e, "ci_red", f"Tests & Build red: {ci.get('failed_jobs', [])[:4]}")
                    self._finish_eject(x)
                    res.ejected.append(x)
                    suspects = [r for r in suspects if r != e.ref]
                    limit = len(suspects) if suspects else batch_limit
                elif ci["verdict"] == "red":
                    culprit, why = self.red_attribution(ci, applied, base)
                    if culprit is not None:
                        self.log(f"  batch red - ATTRIBUTED to {culprit.slug}: {why}; ejecting without bisect")
                        x = self._eject_info(culprit, "ci_red_attributed", why)
                        self._finish_eject(x)
                        res.ejected.append(x)
                        rnd["attribution"] = {"path": "attributed", "reason": why}
                        suspects, limit = [], batch_limit  # the rest were never proven bad: fresh candidate
                    else:
                        suspects = [e.ref for e in applied]
                        limit = next_batch_limit(limit, len(applied), green=False)
                        rnd["attribution"] = {"path": "bisect", "reason": why}
                        self.log(f"  batch red - bisecting ({why}; {len(applied)} entries): next batch limit {limit}")
                else:
                    # timeout/unavailable: leave the entries queued; the next drain retries.
                    for e in applied:
                        self.set_status(e.sha, "pending", f"CI {ci['verdict']} - still queued, will retry")
                    res.rounds.append(rnd)
                    self.delete_ref(cand_ref)
                    break
                res.rounds.append(rnd)
                self.delete_ref(cand_ref)
            finally:
                self.run(["git", "worktree", "remove", "--force", wt], cwd=self.workdir)
                if saved is not None:
                    suspects, limit = saved
        return res

    def _run_wave(self, n: int, groups: list[list[Entry]], base: str, res: Outcome, batch_limit: int,
                  limit: int) -> tuple[list[str], int, bool]:
        """Several area-disjoint candidates composed on the SAME dev base, CI run concurrently (the wall-clock overlap
        is the gain). Returns (suspects, limit, stop). A red candidate ejects/bisects on its own and never touches the
        others. LAND RULE: the first green lands as today; a later green is re-composed on the NEW dev tip and lands
        WITHOUT a CI re-run only if the result is provably the exact union of the two tested trees (see
        `_land_after_peer`); anything else stays queued and the next round re-tests it on the combined tree."""
        suspects: list[str] = []
        stop = False
        wts: list[str] = []
        cands: list[dict[str, Any]] = []

        def scratch() -> str:
            wt = tempfile.mkdtemp(prefix="mq-")
            os.rmdir(wt)
            wts.append(wt)
            return wt

        try:
            for i, group in enumerate(groups, 1):
                wt = scratch()
                cand, applied, ejected = self.compose(group, base, wt)
                for x in ejected:
                    self._finish_eject(x)
                    res.ejected.append(x)
                if not applied:
                    continue
                if cand == base:
                    for e in applied:
                        self._finish_land(e, base)
                        res.landed.append({"slug": e.slug, "dev": base})
                    continue
                ref = f"{CANDIDATE_PREFIX}{self.run_id}-{n}p{i}"
                remote = self.push_remote(self.batch_needs_workflows(base, cand))
                rc, _, perr = self.run(self.push_cmd(remote, f"{cand}:refs/heads/{ref}"), cwd=self.workdir)
                if rc != 0:
                    if self._handle_push_rejection(applied, base, perr, res, via_pat=remote != self.remote):
                        suspects += [e.ref for e in applied if not any(x["ref"] == e.ref for x in res.ejected)]
                    continue
                for e in applied:
                    self.set_status(e.sha, "pending", f"testing in parallel candidate {ref} ({len(applied)} entr{'y' if len(applied) == 1 else 'ies'})")
                cands.append({"ref": ref, "cand": cand, "applied": applied, "wt": wt})
            if not cands:
                return suspects, (next_batch_limit(limit, len(suspects), False) if suspects else batch_limit), False
            tip, landed_paths = base, set()
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(cands)) as pool:
                futs = {pool.submit(self.dispatch_and_wait, c["ref"], c["cand"], base): c for c in cands}
                for fut in concurrent.futures.as_completed(futs):
                    c, applied = futs[fut], futs[fut]["applied"]
                    try:
                        ci = fut.result()
                    except RuntimeError as exc:  # one candidate's gh failure must not strand the others
                        ci = {"verdict": "unavailable", "detail": str(exc)[:200]}
                    rnd = {"round": n, "candidate": c["cand"], "batch": [e.slug for e in applied], "ci": ci, "parallel": True}
                    if ci["verdict"] == "green":
                        if tip == base:
                            ok, landed_sha = self.land(c["cand"], base, c["wt"])
                        else:
                            ok, landed_sha = self._land_after_peer(c, base, tip, landed_paths, scratch)
                        rnd["landed"] = ok
                        if ok:
                            landed_paths |= set(self.changed_paths(tip, landed_sha))
                            for e in applied:
                                self._finish_land(e, landed_sha)
                                res.landed.append({"slug": e.slug, "dev": landed_sha})
                            for wf in post_land_workflows(self.changed_paths(tip, landed_sha)):
                                self.gh("workflow", "run", wf, "--ref", self.dev, "-R", self.repo, check=False)
                                rnd.setdefault("dispatched", []).append(wf)
                            tip = landed_sha
                        else:
                            for e in applied:
                                self.set_status(e.sha, "pending", "green in a parallel candidate, dev moved - still queued, re-tested next round")
                    elif ci["verdict"] == "red":
                        if len(applied) == 1:
                            x = self._eject_info(applied[0], "ci_red", f"Tests & Build red: {ci.get('failed_jobs', [])[:4]}")
                            self._finish_eject(x)
                            res.ejected.append(x)
                        else:
                            culprit, why = self.red_attribution(ci, applied, base)
                            if culprit is not None:
                                x = self._eject_info(culprit, "ci_red_attributed", why)
                                self._finish_eject(x)
                                res.ejected.append(x)
                                rnd["attribution"] = {"path": "attributed", "reason": why}
                            else:
                                suspects += [e.ref for e in applied]
                                limit = next_batch_limit(limit, len(applied), green=False)
                                rnd["attribution"] = {"path": "bisect", "reason": why}
                    else:
                        stop = True  # timeout/unavailable: leave queued, the next drain retries
                        for e in applied:
                            self.set_status(e.sha, "pending", f"CI {ci['verdict']} - still queued, will retry")
                    res.rounds.append(rnd)
            for c in cands:
                self.delete_ref(c["ref"])
        finally:
            for wt in wts:
                self.run(["git", "worktree", "remove", "--force", wt], cwd=self.workdir)
        return suspects, (limit if suspects else batch_limit), stop

    def _land_after_peer(self, c: dict[str, Any], base: str, tip: str, landed_paths: set[str],
                         scratch: Callable[[], str]) -> tuple[bool, str]:
        """Land a green parallel candidate whose peer already moved dev (base -> tip) WITHOUT re-running CI - only when
        the result is provably A (+) B: re-compose its entries on `tip` (this re-runs the kb-counts/derived regen on the
        COMBINED tree), then require (1) the two diffs vs base share no file, (2) the re-composed tree differs from the
        tested candidate only in the peer's files, (3) it differs from `tip` in exactly the candidate's own files.
        Any miss -> (False, "") and the entries stay queued for a real re-test. Residual risk, stated: file-disjoint is
        not effect-disjoint; products-only + no shared file is what keeps it small. KB § PATTERNS/devops/merge-queue.md."""
        self.fetch()
        if self.dev_sha() != tip:
            self.log("  parallel candidate green but dev moved beyond the wave - re-test next round")
            return False, ""
        wt2 = scratch()
        cand2, applied2, ejected2 = self.compose(c["applied"], tip, wt2)
        if ejected2 or len(applied2) != len(c["applied"]) or cand2 == tip:
            self.log("  parallel candidate did not re-compose cleanly on the new tip - re-test next round")
            return False, ""
        own = set(self.changed_paths(base, c["cand"]))
        if own & landed_paths:
            self.log(f"  parallel candidates overlap on {sorted(own & landed_paths)[:3]} - re-test next round")
            return False, ""
        if not set(self.changed_paths(c["cand"], cand2)) <= landed_paths or set(self.changed_paths(tip, cand2)) != own:
            self.log("  combined tree is not exactly the union of the tested trees (derived files moved) - re-test next round")
            return False, ""
        self.log("  parallel candidate is exactly peer+own on the new tip - landing without a CI re-run")
        return self.land(cand2, tip, wt2)

    def _handle_push_rejection(self, applied: list[Entry], base: str, stderr: str, res: Outcome,
                               via_pat: bool = False) -> bool:
        """A candidate push was rejected. Eject the culprit(s) and return True when the batch must still be
        bisected (cause not attributable to a single entry).

        The eject reason names WHICH credential GitHub refused and quotes GitHub's own line: "the queue's
        token cannot push workflow edits" is a different fix when the refused push already went out with
        MQ_PUSH_TOKEN (the PAT lost `workflows` / expired - the owner re-mints) than with github.token
        (no PAT configured - set it). 2026-11-11: five entries were ejected with neither fact recorded."""
        stderr = self._redact(stderr or "")
        tail = stderr.strip()[-300:]
        who = "MQ_PUSH_TOKEN (PAT)" if via_pat else "github.token"
        self.log(f"  candidate push via {who} rejected:\n{tail}")
        if is_workflow_rejection(stderr):
            culprits = [e for e in applied if touches_workflows(self.changed_paths(base, e.sha))]
            m = WORKFLOW_REJECT_LINE_RE.search(stderr)
            said = (m.group(0) if m else tail)[-160:]
            remedy = ("the PAT itself was refused - re-mint MQ_PUSH_TOKEN with Workflows: write" if via_pat
                      else WORKFLOW_EJECT_WHY)
            kind, why = "needs_workflow_token", f"push via {who} refused ({said}) - {remedy}"
        else:
            culprits = applied if len(applied) == 1 else []
            kind, why = "push_rejected", f"candidate push rejected: {tail}"
        if not culprits and len(applied) == 1:
            culprits = applied
        for e in culprits:
            x = self._eject_info(e, kind, why)
            self._finish_eject(x)
            res.ejected.append(x)
        left = [e for e in applied if e not in culprits]
        if left:
            self.log(f"  candidate push rejected ({kind}); {len(left)} entr{'y' if len(left) == 1 else 'ies'} stay queued")
        return bool(left) and not culprits

    def _finish_land(self, e: Entry, dev_sha: str) -> None:
        self.set_status(e.sha, "success", f"landed in dev as {dev_sha[:9]}")
        self.delete_ref(e.ref)
        self.log(f"  LANDED {e.slug} -> dev {dev_sha[:9]}")

    def _finish_eject(self, x: dict[str, Any]) -> None:
        self.set_status(x["sha"], "failure", f"ejected ({x['kind']}): {x['why']}")
        self.delete_ref(x["ref"])
        self.log(f"  EJECTED {x['slug']}: {x['kind']} - {x['why']}")


def read_status(repo: str, sha: str, run: Runner = _default_run) -> dict[str, Any]:
    """The queue verdict for an enqueued sha: queued | pending | landed | ejected | unknown."""
    rc, out, err = run(["gh", "api", f"repos/{repo}/commits/{sha}/statuses", "--jq",
                        f'[.[] | select(.context=="{STATUS_CONTEXT}")][0]'])
    if rc != 0:
        return {"state": "unavailable", "detail": err.strip()[:300]}
    if not out.strip() or out.strip() == "null":
        return {"state": "queued", "detail": "no merge-queue verdict yet"}
    try:
        s = json.loads(out)
    except json.JSONDecodeError as exc:  # a gh banner / partial body is "unavailable", never a crash
        return {"state": "unavailable", "detail": f"unparseable gh output: {exc}: {out.strip()[:200]}"}
    state = {"success": "landed", "failure": "ejected", "error": "ejected"}.get(s.get("state"), "pending")
    m = re.search(r"landed in dev as ([0-9a-f]{7,40})", s.get("description") or "")
    return {"state": state, "description": s.get("description"), "url": s.get("target_url"),
            **({"dev_sha": m.group(1)} if m else {})}


def queue_snapshot(repo: str = "", run: Runner = _default_run, workdir: str | None = None) -> dict[str, Any]:
    """The queue as it is NOW. RAISES on a git/gh failure (callers decide: `queue_report`
    folds it into an error object, `watch` retries and keeps its last good snapshot)."""
    q = Queue(repo, run=run, workdir=workdir)
    q.repo = repo or _repo_from_remote(run, q.workdir)
    q.fetch()
    entries = q.entries()
    return {"status": "ok", "dev": q.dev_sha(), "count": len(entries),
            "entries": [{"slug": e.slug, "ref": e.ref, "sha": e.sha,
                         "verdict": listed_verdict(read_status(q.repo, e.sha, run=run))} for e in entries]}


def listed_verdict(v: dict[str, Any]) -> dict[str, Any]:
    """The verdict of an entry that is STILL LISTED. The verdict is a commit status on the sha, so re-enqueueing the
    same sha after an eject keeps the old run's `failure` as its newest status (2026-11-12: the watch printed
    mq-ref-delete b363927bb "ejected (needs_workflow_token)" from drain 43111891747 for a fresh entry). A listed ref is
    never terminal - the drain removes it when it lands or ejects - so a terminal state here belongs to an earlier
    enqueue: report `queued`, naming the stale verdict. The leaving path (`read_status` by sha) is unchanged: by then
    the drain has written the new verdict."""
    if v.get("state") not in ("landed", "ejected"):
        return v
    stale = " ".join(x for x in (str(v.get("description") or ""), str(v.get("url") or "")) if x)
    return {"state": "queued", "detail": f"re-enqueued; the sha's previous verdict is stale ({v['state']}: {stale})"[:400]}


def error_report(exc: BaseException) -> dict[str, Any]:
    """The one shape every failure path prints: a JSON object with status=error (never a bare
    traceback — 2026-11-05 a failed `git fetch` printed no JSON and the steward's scraper
    died on `substring not found`, missing 6 transitions)."""
    return {"status": "error", "error_type": type(exc).__name__, "error": str(exc)[:500]}


def queue_report(repo: str = "", run: Runner = _default_run, workdir: str | None = None) -> dict[str, Any]:
    """Read-only: what is waiting in the queue, oldest first, with each entry's verdict.
    Never raises: a failure is `{status: "error", error_type, error}`."""
    try:
        return queue_snapshot(repo, run=run, workdir=workdir)
    except Exception as exc:  # noqa: BLE001 - boundary: every failure becomes a JSON error object
        return error_report(exc)


def _fmt_entry_line(slug: str, sha: str, v: dict[str, Any]) -> str:
    tail = " ".join(x for x in (str(v.get("description") or v.get("detail") or ""), str(v.get("url") or "")) if x)
    return f"MQ {slug} {sha[:9]} -> {v.get('state', 'unknown')}: {tail}".rstrip()


def watch(list_fn: Callable[[], dict[str, Any]], status_fn: Callable[[str], dict[str, Any]],
          interval: float = 60, sleep: Callable[[float], None] = time.sleep,
          emit: Callable[[str], None] = lambda line: print(line, flush=True),
          max_polls: int | None = None, attempts: int = 3, left_retries: int = 10,
          batches_fn: Callable[[], list[dict[str, Any]]] | None = None) -> None:
    """Long-running transition printer: ONE line per change, so a steward never diffs by hand.

    `MQ <slug> <sha9> -> <state>: <desc> <url>` when a listed entry's verdict changes (and once
    for each entry on first sight); `MQ-LEFT <slug> <sha9> -> landed <dev_sha> | ejected <reason>`
    when an entry leaves the list (its final verdict is read by sha; a not-yet-readable verdict
    is retried on later polls, never dropped). A failing read is retried with backoff, then
    reported as `MQ-WATCH-ERROR <type>: <msg>` while the last good snapshot is KEPT, so the next
    successful poll still reports every transition that happened in between. Never exits on a
    transient error (only KeyboardInterrupt / `max_polls`, for tests).

    With `batches_fn` (completed candidate runs: [{id, branch, conclusion, url}]) it also
    prints `MQ-BATCH <branch> -> <conclusion> <url>` once per candidate batch that finishes
    after the first poll (the first poll is a silent baseline). A red or cancelled batch is
    the one event an entry-only watch never shows: a bisect replays the same entries for
    hours with nothing leaving the list (2026-11-08: 3.5 h silent; 2026-11-09: the owner
    caught batch 9's red before the steward did)."""
    known: dict[str, dict[str, Any]] = {}   # sha -> {slug, state, line}
    leaving: dict[str, dict[str, Any]] = {}  # sha -> {slug, tries}
    seen_batches: set[str] | None = None     # None until the silent baseline poll
    polls = 0
    while max_polls is None or polls < max_polls:
        polls += 1
        if batches_fn is not None:
            try:
                done = batches_fn()
            except Exception as exc:  # noqa: BLE001 - a failed batch read is reported, never fatal
                emit(f"MQ-WATCH-ERROR batches {type(exc).__name__}: {str(exc)[:300]}")
            else:
                ids = {str(b.get("id")) for b in done}
                if seen_batches is None:
                    seen_batches = ids
                else:
                    for b in done:
                        if str(b.get("id")) not in seen_batches:
                            emit(f"MQ-BATCH {b.get('branch', '?')} -> {b.get('conclusion') or 'unknown'} "
                                 f"{b.get('url', '')}".rstrip())
                    seen_batches |= ids
        report: dict[str, Any] | None = None
        err: BaseException | None = None
        for i in range(attempts):
            try:
                report = list_fn()
                if report.get("status") == "error":
                    err = RuntimeError(f"{report.get('error_type', 'Error')}: {report.get('error')}")
                    report = None
                else:
                    err = None
                    break
            except Exception as exc:  # noqa: BLE001 - never die on a transient
                err = exc
            if i < attempts - 1:
                sleep(min(2 ** i, interval))
        if report is None:
            emit(f"MQ-WATCH-ERROR {type(err).__name__}: {str(err)[:300]}")
        else:
            current = {e["sha"]: e for e in report.get("entries", [])}
            for sha, e in current.items():
                v = e.get("verdict", {})
                prev = known.get(sha)
                if v.get("state") == "unavailable" and prev:
                    continue  # a flaky status read is not a transition
                if prev is None or prev["state"] != v.get("state"):
                    emit(_fmt_entry_line(e["slug"], sha, v))
                known[sha] = {"slug": e["slug"], "state": v.get("state")}
                leaving.pop(sha, None)
            for sha in [s for s in known if s not in current]:
                leaving[sha] = {"slug": known.pop(sha)["slug"], "tries": 0}
        for sha in list(leaving):
            slug = leaving[sha]["slug"]
            try:
                v = status_fn(sha)
            except Exception as exc:  # noqa: BLE001
                v = {"state": "unavailable", "detail": f"{type(exc).__name__}: {exc}"}
            st = v.get("state")
            if st == "landed":
                emit(f"MQ-LEFT {slug} {sha[:9]} -> landed {v.get('dev_sha', '')}".rstrip())
            elif st == "ejected":
                emit(f"MQ-LEFT {slug} {sha[:9]} -> ejected {v.get('description') or v.get('detail') or ''}".rstrip())
            else:
                leaving[sha]["tries"] += 1
                if leaving[sha]["tries"] >= left_retries:
                    emit(f"MQ-LEFT {slug} {sha[:9]} -> unknown (no final verdict after {left_retries} polls: {st})")
                else:
                    continue
            leaving.pop(sha, None)
        if max_polls is not None and polls >= max_polls:
            break
        sleep(interval)


def watch_live(interval: float = 60, run: Runner = _default_run, workdir: str | None = None) -> None:
    """`watch` against the real repo: the list is read IN-PROCESS (no subprocess/JSON scrape)."""
    wd = workdir or os.getcwd()
    repo = _repo_from_remote(run, wd)
    watch(lambda: queue_snapshot(repo, run=run, workdir=wd),
          lambda sha: read_status(repo, sha, run=run), interval=interval,
          batches_fn=lambda: completed_candidate_runs(run=run, workdir=wd))


def completed_candidate_runs(run: Runner = _default_run, workdir: str | None = None,
                             limit: int = 40) -> list[dict[str, Any]]:
    """The completed `mq-candidate/*` test runs among the newest `limit` runs. Raises on a
    failed read, so `watch` reports it instead of mistaking silence for a green queue."""
    rc, out, err = run(["gh", "run", "list", "-L", str(limit), "--json",
                        "databaseId,headBranch,status,conclusion,url"], cwd=workdir)
    if rc != 0:
        raise RuntimeError(f"gh run list failed: {(err or out or '').strip()[:200]}")
    rows = json.loads(out or "[]")
    return [{"id": r.get("databaseId"), "branch": r.get("headBranch", ""),
             "conclusion": r.get("conclusion", ""), "url": r.get("url", "")}
            for r in rows
            if str(r.get("headBranch", "")).startswith(CANDIDATE_PREFIX) and r.get("status") == "completed"]


def _repo_from_remote(run: Runner, cwd: str) -> str:
    rc, out, _ = run(["git", "remote", "get-url", "origin"], cwd=cwd)
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?\s*$", out or "")
    return m.group(1) if rc == 0 and m else ""


def register(server) -> None:  # pragma: no cover - thin MCP wrapper
    @server.tool(
        name="noctus.dev.merge_queue",
        description=(
            "Read-only view of the CI merge queue — the one path code takes into dev "
            "(KB § PATTERNS/devops/merge-queue.md). action='list' (default): entries "
            "waiting (oldest first) with each one's merge-queue verdict; action='status' "
            "sha=<enqueued sha>: queued | pending | landed (+dev sha) | ejected (+why). "
            "Enqueue/land with noctus.dev.task_branch action='enqueue' / 'landed'. The "
            "drain itself runs only on GitHub Actions (.github/workflows/merge-queue.yml)."),
    )
    def noctus_dev_merge_queue(action: str = "list", sha: str | None = None) -> dict[str, Any]:
        if action == "status":
            if not sha:
                return {"status": "error", "error": "action='status' needs sha="}
            return read_status(_repo_from_remote(_default_run, os.getcwd()), sha)
        return queue_report()


def _summary(res: Outcome) -> str:
    lines = ["## Merge queue", ""]
    for x in res.landed:
        lines.append(f"- ✅ landed `{x['slug']}` → dev `{x['dev'][:9]}`")
    for x in res.ejected:
        lines.append(f"- ❌ ejected `{x['slug']}` ({x['kind']}): {x['why']}")
    for r in res.rounds:
        ci = r.get("ci", {})
        lines.append(f"- round {r['round']}: {r.get('batch')} → CI {ci.get('verdict', '-')} {ci.get('url', '')}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["drain", "list", "status", "watch"])
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sha", help="status: the enqueued sha")
    ap.add_argument("--interval", type=float, default=60, help="watch: poll interval, seconds")
    a = ap.parse_args(argv)
    if a.command == "watch":
        try:
            watch_live(a.interval)
        except KeyboardInterrupt:
            return 0
    if a.command == "status":
        print(json.dumps(read_status(a.repo, a.sha), indent=2))
        return 0
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{a.repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    q = Queue(a.repo, run_url=run_url, run_id=os.environ.get("GITHUB_RUN_ID", "local"))
    if a.command == "list":
        q.fetch()
        print(json.dumps([e.__dict__ for e in q.entries()], indent=2))
        return 0
    res = q.drain(batch_limit=a.batch, dry_run=a.dry_run)
    text = _summary(res)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
