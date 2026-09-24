"""noctus.dev.release — the dev→main (bless) + main→prod (promote) gates as a tool.

`main` is sacred (KB § PATTERNS/branching-and-merging.md § 0). Two deliberate,
consent-gated hops sit between everyday `dev` work and the live VPS:

  • Gate 1 — BLESS  : fast-forward `main` to the `dev` tip (a reviewed release).
                      `sha=` is NOT accepted here — bless always means "the
                      WHOLE dev-validated state", never a partial slice
                      (KB § PATTERNS/architect/git-branch-model.md); passing it
                      is REFUSED loudly (2026-07-20 — it used to be a SILENT
                      no-op that still blessed the dev tip while the caller
                      believed their pin had taken effect). It also REFUSES
                      unless `Tests & Build` is GREEN on the exact dev tip
                      (2026-08-22 — see below).
  • RIDERS (2026-09-22; relaxed 2026-09-24) — `stage=manifest` attributes
                      every commit main..dev (Noc-Branch trailer → branch-tree
                      project) to a ship-consent state. Since 2026-09-24 that
                      state is INFORMATIONAL for the default mode='ff': the
                      owner's request to ship is the permission, so bless FFs
                      the whole CI-green dev tip. mode='cut' (opt-in) still
                      builds a `release/<stamp>` of approved work only
                      (merge-tree + commit-tree, no checkout), and
                      `stage=backmerge` restores dev ⊇ main after a cut.
                      KB § PATTERNS/devops/ship-consent-riders.md.
  • Gate 2 — PROMOTE: fast-forward `prod` to a blessed `main` sha — and FIRST
                      snapshot the *current* prod onto `prod-backup` (instant
                      rollback pointer). The VPS pulls `origin/prod` afterwards
                      via `noctus.dev.deploy_pull`. `sha=` IS accepted here —
                      pin promote to an earlier-blessed main sha instead of
                      main's current tip.

This tool is the ONLY sanctioned path that sets `NOCTUS_ALLOW_MAIN_PUSH=1` (the
pre-push hook's override) — and it does so ONLY for its own confirm-gated push.
Every other push to `main`/`prod` stays blocked by `scripts/hooks/pre-push`. So
you stop managing the env var by hand: dry-run → review the plan → confirm=True.

Safety model (mirrors deploy_pull / the §2a stack):
  • INSPECT (always, read-only): fetch refs, resolve the four branch tips,
    compute fast-forward-ability + the commit list each hop would ship.
  • DECIDE (deterministic): a hop proceeds ONLY as a clean fast-forward
    (target's current tip is an ancestor of the source). Never a force.
  • confirm-GATE (412 pattern): without `confirm`, returns the PLAN only — no
    ref moves. A non-FF (or a `sha` not contained in `main`) is REFUSED, not
    forced — the refusal IS the safety net.
  • BY CONSTRUCTION it only runs a safe git allowlist (fetch / rev-parse /
    merge-base / rev-list / log / push) and never carries reset/checkout/clean/
    --force/--force-with-lease (a colocated test asserts this across a confirmed
    bless AND a confirmed promote). The one non-git call is a read-only
    `gh run list` (the CI probe below); a colocated test pins the subcommand.
  • CI-GREEN is a bless PRECONDITION, not a checklist line (2026-08-22).
    `noc-ship` step 0b called it MANDATORY for months while NOTHING checked it,
    so `1c83232f` was blessed AND promoted to prod carrying a red
    `Tests & Build`, and `dev` then stayed red for 12 commits with the gate
    reading as satisfied. Bless now probes the exact dev tip and refuses on
    red / pending / missing / unreachable alike — REFUSE-NOT-NULL, because "I
    could not find out" is not "it passed". The sole exception is the one the
    skill already names: a diff that touches nothing executable (docs +
    project-history only). There is deliberately NO override flag; a red dev
    is fixed on dev. → KB § PATTERNS/devops/dev-main-ci-gates.md.

IO is injectable (`run`, `now`) so the colocated test drives every path with
zero real git and asserts both the allowlist and the NOCTUS_ALLOW_MAIN_PUSH
discipline (set on main/prod pushes, NEVER on the prod-backup snapshot push).
"""
from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any, Callable

# git subcommands the tool may run. It pushes ref-specs (`<sha>:refs/heads/X`),
# never checks out / resets / forces — keeping those off the list makes a
# destructive or history-rewriting release structurally impossible.
# 2026-09-22 (ship-consent riders): + read-only `show`/`cherry`/`cat-file`/
# `patch-id` for the rider manifest, and `merge-tree`/`commit-tree` for the
# release CUT — both write only unreachable OBJECTS (never a ref, never a
# working tree, never an index), so a cut is a cherry-pick with no checkout.
# Refs still move ONLY via `push`.
_ALLOWED_GIT = frozenset({
    "fetch", "rev-parse", "merge-base", "rev-list", "log", "diff", "push",
    "show", "cherry", "cat-file", "patch-id", "merge-tree", "commit-tree",
})

# The CI workflow whose green is a bless PRECONDITION (skill `noc-ship` step 0b).
_CI_WORKFLOW = "Tests & Build"
_BANNED_TOKENS = (
    "reset", "checkout", "restore", "clean", "--hard", "--force",
    "--force-with-lease", "-D", "branch",
)

# Reuse the deploy_pull rebuild oracle so a promote tells you whether the VPS
# pull will need a container rebuild — DRY, one source of truth.
from tools.noctus.dev.deploy_pull import _rebuild_decision  # noqa: E402
from tools.noctus.dev import toolkit_freshness as _toolkit_freshness  # noqa: E402


def _default_run_local(
    cmd: list[str], env_extra: dict[str, str] | None = None, stdin: str | None = None
) -> tuple[int, str, str]:
    """Run `cmd` locally at the repo root; (rc, stdout, stderr). `env_extra`
    overlays the process env (used to set NOCTUS_ALLOW_MAIN_PUSH on the one
    sanctioned push). REPO_ROOT is imported lazily so module import stays light
    and the test (which injects `run`) never pays the settings import cost."""
    import os

    from settings import REPO_ROOT  # lazy: avoids import-time noctusai_lib cost

    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    # surrogateescape: `git log -p` carries arbitrary bytes (binary diffs, Latin-1
    # sources). Strict utf-8 crashed stage=manifest on 2026-09-23; surrogateescape
    # round-trips every byte exactly, so the text handed back to `git patch-id`
    # on stdin is byte-identical to what git produced.
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="surrogateescape", cwd=str(REPO_ROOT), env=env,
                       input=stdin)
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _git(runner, *args, env_extra: dict[str, str] | None = None,
         stdin: str | None = None) -> tuple[int, str, str]:
    """Run a git subcommand — ONLY if on the safe allowlist AND carrying no
    banned token. The structural guarantee the tool can never force/rewrite."""
    sub = args[0] if args else ""
    if sub not in _ALLOWED_GIT:
        raise ValueError(
            f"release: git '{sub}' is not on the safe allowlist {sorted(_ALLOWED_GIT)}"
        )
    for tok in args:
        if tok in _BANNED_TOKENS:
            raise ValueError(f"release: banned token '{tok}' in git {list(args)}")
    if stdin is not None:
        return runner(["git", *args], env_extra=env_extra, stdin=stdin)
    return runner(["git", *args], env_extra=env_extra) if env_extra is not None \
        else runner(["git", *args])


def _resolve(git, ref: str) -> str | None:
    rc, out, _e = git("rev-parse", ref)
    return out.strip() if rc == 0 and out.strip() else None


def _is_ancestor(git, a: str, b: str) -> bool:
    """True iff commit `a` is an ancestor of (or equal to) `b` — i.e. b can
    fast-forward from a."""
    rc, _o, _e = git("merge-base", "--is-ancestor", a, b)
    return rc == 0


def _commits(git, a: str, b: str) -> list[str]:
    rc, out, _e = git("log", "--oneline", f"{a}..{b}")
    return [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []


def _changed_paths(git, a: str, b: str) -> list[str]:
    rc, out, _e = git("diff", "--name-only", f"{a}..{b}")
    return [ln.strip() for ln in out.splitlines() if ln.strip()] if rc == 0 else []


def _is_docs_only(paths: list[str]) -> bool:
    """The ONE sanctioned CI exception (skill `noc-ship` step 0b): a diff that
    ships no executable change. Empty is NOT docs-only — an unreadable diff
    must not buy a pass."""
    return bool(paths) and all(
        p.endswith(".md") or p.startswith(("project-history/", "docs/"))
        for p in paths
    )


def _ci_verdict(runner, sha: str, workflow: str = _CI_WORKFLOW) -> dict[str, Any]:
    """The CI conclusion for `workflow` on EXACTLY `sha`.

    verdict ∈ {green, red, pending, missing, unavailable}. Everything that is
    not `green` refuses the bless — REFUSE-NOT-NULL: "I could not find out" is
    not "it passed" (2026-08-22: `1c83232f` was blessed AND promoted to prod
    while this workflow was red, because nothing but agent discipline checked).
    """
    rc, out, err = runner([
        "gh", "run", "list", "--workflow", workflow, "--commit", sha,
        "--limit", "20", "--json", "status,conclusion,url",
    ])
    if rc != 0:
        return {"verdict": "unavailable", "workflow": workflow,
                "detail": (err.strip() or out.strip())[:300]}
    try:
        runs = json.loads(out or "[]")
    except json.JSONDecodeError as exc:
        return {"verdict": "unavailable", "workflow": workflow,
                "detail": f"unparseable `gh run list` output: {exc}"}
    if not runs:
        return {"verdict": "missing", "workflow": workflow,
                "detail": f"no '{workflow}' run exists for {sha[:9]}"}
    # Newest first. `cancelled`/`skipped` carry no verdict — a superseded run
    # must not decide, and must not be mistaken for a pass either.
    for run in runs:
        if run.get("status") != "completed":
            return {"verdict": "pending", "workflow": workflow, "url": run.get("url"),
                    "detail": f"run is {run.get('status')} — wait for it"}
        concl = run.get("conclusion")
        if concl in (None, "cancelled", "skipped"):
            continue
        return {"verdict": "green" if concl == "success" else "red",
                "workflow": workflow, "conclusion": concl, "url": run.get("url")}
    return {"verdict": "missing", "workflow": workflow,
            "detail": f"every '{workflow}' run on {sha[:9]} was cancelled/skipped"}


# ── ship-consent riders (2026-09-22) ─────────────────────────────────────────
# Owner mandate: a prod deploy must NOT carry other agents' in-flight /
# unapproved work. Bless used to FF main to the WHOLE dev tip; it now reads a
# rider MANIFEST (every commit main..dev, grouped Noc-Branch → project →
# ship-consent state) and, when anything is unapproved, defaults to CUTTING a
# `release/<stamp>` branch of approved work only.
# KB § PATTERNS/devops/ship-consent-riders.md.
_CONSENT_LEDGER_REL = "project-history/ship-consent.ndjson"
_POINTER_LEDGER_REL = "project-history/branch-tree.ndjson"
_MODES = ("ff", "cut", "refuse")


def _read_ledger(git, remote: str, dev_branch: str, rel: str) -> list[dict]:
    """dev's copy of an append-only ledger (what every agent sees). Absent ⇒
    [] (no approvals / no pointers yet is a real state, not an error)."""
    rc, out, _e = git("show", f"{remote}/{dev_branch}:{rel}")
    if rc != 0:
        return []
    rows = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            rows.append(rec)
    return rows


def _manifest(git, main: str, dev: str, remote: str, dev_branch: str,
              consent_rows, pointer_rows, verify_consent, transcript_home) -> dict[str, Any]:
    from tools.noctus.dev import _release_riders as RR
    from tools.noctus.dev.branch_pointer import project_for_branch
    from tools.noctus.dev.ship_consent import effective_approvals, verify_row

    if consent_rows is None:
        consent_rows = _read_ledger(git, remote, dev_branch, _CONSENT_LEDGER_REL)
    if pointer_rows is None:
        pointer_rows = _read_ledger(git, remote, dev_branch, _POINTER_LEDGER_REL)
    verify = verify_consent or (lambda row: verify_row(row, home=transcript_home))
    return RR.build_manifest(git, main, dev, consent_rows, pointer_rows, verify,
                             project_for_branch, effective_approvals)


def _stamp(now) -> str:
    import datetime as _dt
    t = now() if callable(now) else now
    t = t or _dt.datetime.now(_dt.timezone.utc)
    return t.strftime("%Y%m%d-%H%M")


def _bless_cut(git, base, man, mode, confirm, remote, main, main_branch,
               dev_branch, ff, now) -> dict[str, Any]:
    """Unapproved riders (or a diverged main after an earlier cut): never FF
    the whole dev tip. mode='refuse' → blocked; mode='cut' (default) → build
    `release/<stamp>` = main + approved/exempt commits in dev order."""
    from tools.noctus.dev._release_riders import cherry_pick_chain

    info = {"unapproved_riders": man["unapproved_riders"], "projects": man["projects"],
            "deferred": man["deferred"], "ff": ff}
    if mode == "refuse":
        return {**base, **info, "status": "blocked", "exit_code": 1,
                "reason": (f"{len(man['unapproved_riders'])} rider(s) lack ship-consent"
                           + ("" if ff else f"; {main_branch} is not an ancestor of "
                              f"{dev_branch} (run stage='backmerge' after a cut)")
                           + ". Approve via noctus.dev.ship_consent, or bless mode='cut'.")}
    if man["dependencies"]:
        return {**base, **info, "status": "blocked", "exit_code": 1,
                "dependencies": man["dependencies"],
                "reason": "an APPROVED commit changes files last changed by an UNAPPROVED "
                          "rider before it — shipping it alone would ship a state that never "
                          "existed on dev. Approve the named rider's project, or wait for it: "
                          + "; ".join(f"{d['commit'][:9]} needs {', '.join(x[:9] for x in d['depends_on'])}"
                                      for d in man["dependencies"])}
    if not man["ship"]:
        return {**base, **info, "status": "blocked", "exit_code": 1,
                "reason": "nothing approved to ship — every rider awaits ship-consent "
                          "(or is already on main)."}
    chain = cherry_pick_chain(git, main, man["ship"])
    if not chain["ok"]:
        return {**base, **info, "status": "blocked", "exit_code": 1,
                "conflict": chain.get("conflict"), "detail": chain.get("detail"),
                "reason": (f"approved commit {str(chain.get('conflict') or '')[:9]} does not "
                           f"apply cleanly onto {main_branch} without the riders left behind — "
                           "it depends on unapproved work. " + str(chain.get("error") or ""))}
    name = f"release/{_stamp(now)}"
    plan = {**base, **info, "mode": "cut", "release_branch": name,
            "release_sha": chain["tip"], "ship": man["ship"], "picked": chain["picked"],
            "would_advance": f"{remote}/{name} → {chain['tip'][:9]} "
                             f"({len(man['ship'])} commit(s) on {main[:9]})"}
    if not confirm:
        return {**plan, "status": "planned_cut", "exit_code": 0,
                "message": (f"cut planned: {len(man['ship'])} approved/exempt commit(s), "
                            f"{len(man['unapproved_riders'])} rider(s) left on {dev_branch}. "
                            "confirm=True pushes the release branch (NOT main).")}
    rc, out, err = git("push", remote, f"{chain['tip']}:refs/heads/{name}")
    if rc != 0:
        return {**plan, "status": "error", "exit_code": 1,
                "error": f"push of {name} failed: {err.strip() or out.strip()}"}
    return {**plan, "status": "cut_pushed", "exit_code": 0,
            "message": (f"pushed {name} @ {chain['tip'][:9]}. Wait for '{_CI_WORKFLOW}' "
                        f"GREEN on that sha, then noctus.dev.release stage='bless' "
                        f"release_branch='{name}' confirm=True. After promote: "
                        "stage='backmerge'.")}


def _bless_release_branch(git, runner, base, manifest, remote, main, main_branch,
                          release_branch, confirm) -> dict[str, Any]:
    """FF main → a pushed cut, after RE-verifying (a) it is still a pure cut of
    currently-approved work and (b) CI is green on its exact sha."""
    from tools.noctus.dev._release_riders import release_branch_sources

    if not release_branch.startswith("release/"):
        return {**base, "status": "error", "exit_code": 1,
                "error": f"release_branch must be a release/<stamp> cut (got {release_branch!r})"}
    rel = _resolve(git, f"{remote}/{release_branch}")
    if not rel:
        return {**base, "status": "error", "exit_code": 1,
                "error": f"cannot resolve {remote}/{release_branch}"}
    if not _is_ancestor(git, main, rel):
        return {**base, "status": "blocked", "exit_code": 1, "release_sha": rel,
                "reason": f"{main_branch} moved since the cut — cut again (never force main)."}
    sources, err = release_branch_sources(git, main, rel)
    man = manifest()
    if err or not man.get("ok"):
        return {**base, "status": "blocked", "exit_code": 1,
                "reason": f"cannot verify the cut: {err or man.get('error')}"}
    shippable = set(man["ship"]) | set(man.get("on_main") or [])
    foreign = [s["sha"][:9] for s in sources
               if s["merge"] or not s["from"] or s["from"] not in shippable]
    if foreign:
        return {**base, "status": "blocked", "exit_code": 1, "release_sha": rel,
                "foreign_commits": foreign,
                "reason": ("the release branch carries commits that are not cuts of "
                           "CURRENTLY-approved work (hand-added, or consent revoked since): "
                           + ", ".join(foreign))}
    ci = _ci_verdict(runner, rel)
    docs_only = _is_docs_only(_changed_paths(git, main, rel))
    if ci["verdict"] != "green" and not docs_only:
        return {**base, "status": "blocked", "exit_code": 1, "ci": ci, "release_sha": rel,
                "reason": f"CI is not green on the release sha {rel[:9]} "
                          f"(verdict={ci['verdict']}): {ci.get('detail') or ci.get('url') or ''}"}
    plan = {**base, "release_branch": release_branch, "release_sha": rel, "ci": ci,
            "incoming_commits": _commits(git, main, rel),
            "would_advance": f"{main_branch} → {rel[:9]} ({release_branch})"}
    if not confirm:
        return {**plan, "status": "planned", "exit_code": 0,
                "message": f"clean FF {main_branch} → {release_branch}. Pass confirm=True."}
    rc, out, err = git("push", remote, f"{rel}:refs/heads/{main_branch}",
                       env_extra={"NOCTUS_ALLOW_MAIN_PUSH": "1"})
    if rc != 0:
        return {**plan, "status": "error", "exit_code": 1,
                "error": f"push to {main_branch} failed: {err.strip() or out.strip()}"}
    new_main = _resolve(git, f"{remote}/{main_branch}")
    return {**plan, "status": "blessed", "exit_code": 0, "new_main_sha": new_main,
            "verified": new_main == rel,
            "message": f"blessed {release_branch} to {main_branch}. Next: stage='promote', "
                       "then stage='backmerge' so dev ⊇ main again."}


@_toolkit_freshness.refuse_gate("release")
def release(
    stage: str = "status",
    confirm: bool = False,
    remote: str = "origin",
    dev_branch: str = "dev",
    main_branch: str = "main",
    prod_branch: str = "prod",
    backup_branch: str = "prod-backup",
    sha: str | None = None,
    mode: str = "ff",
    release_branch: str | None = None,
    run: Callable[..., tuple[int, str, str]] | None = None,
    now=None,  # datetime | () -> datetime — stamps release/<YYYYMMDD-HHMM>
    consent_rows: list[dict] | None = None,
    pointer_rows: list[dict] | None = None,
    verify_consent: Callable[[dict], tuple[bool, str]] | None = None,
    transcript_home=None,
) -> dict[str, Any]:
    """`stage` ∈ {status, manifest, bless, promote, backmerge}. Dry-run unless
    `confirm`. Returns a structured plan/result; never raises on a refusal —
    it returns it. `consent_rows`/`pointer_rows`/`verify_consent` are DI seams
    (default: dev's ledgers + transcript re-verification)."""
    runner = run or _default_run_local

    def git(*args, env_extra=None, stdin=None):
        return _git(runner, *args, env_extra=env_extra, stdin=stdin)

    if stage not in {"status", "manifest", "bless", "promote", "backmerge"}:
        return {"ok": False, "status": "error", "exit_code": 1,
                "error": f"unknown stage '{stage}' "
                         "(expected status|manifest|bless|promote|backmerge)"}
    if mode not in _MODES:
        return {"ok": False, "status": "error", "exit_code": 1,
                "error": f"unknown mode '{mode}' (expected {'|'.join(_MODES)})"}

    # ── INSPECT (read-only) ──
    git("fetch", remote, "--quiet")
    dev = _resolve(git, f"{remote}/{dev_branch}")
    main = _resolve(git, f"{remote}/{main_branch}")
    prod = _resolve(git, f"{remote}/{prod_branch}")
    backup = _resolve(git, f"{remote}/{backup_branch}")
    if not (dev and main):
        return {"ok": False, "status": "error", "exit_code": 1,
                "error": f"cannot resolve {remote}/{dev_branch} or {remote}/{main_branch} "
                         "(fetch failed or branch missing)"}

    base: dict[str, Any] = {
        "ok": True, "remote": remote, "stage": stage,
        "dev_sha": dev, "main_sha": main, "prod_sha": prod, "backup_sha": backup,
    }

    # ── STATUS ── full chain overview, no writes ever
    if stage == "status":
        bless_ff = _is_ancestor(git, main, dev)
        dev_ci = _ci_verdict(runner, dev)
        promote_ff = bool(prod) and _is_ancestor(git, prod, main)
        return {
            **base, "status": "status", "exit_code": 0,
            "bless": {  # dev → main
                "ff": bless_ff, "ahead": len(_commits(git, main, dev)),
                "commits": _commits(git, main, dev)[:20],
                # not-green here BLOCKS bless (unless the diff is docs-only)
                "ci": dev_ci,
            },
            "promote": {  # main → prod (ships EVERYTHING main is ahead of prod)
                "ff": promote_ff,
                "ahead": len(_commits(git, prod, main)) if prod else None,
                "commits": _commits(git, prod, main)[:20] if prod else [],
            },
            "prod_backup_trails_prod": (backup == prod) if (backup and prod) else None,
            "message": "chain: feat/* → dev → main (bless) → prod (promote) → VPS (deploy_pull). "
                       "Before bless: stage='manifest' shows WHOSE work the bless would carry "
                       "and its ship-consent state.",
        }

    def manifest():
        return _manifest(git, main, dev, remote, dev_branch, consent_rows,
                         pointer_rows, verify_consent, transcript_home)

    # ── MANIFEST ── read-only: who rides along, and are they approved?
    if stage == "manifest":
        man = manifest()
        if not man.get("ok"):
            return {**base, "status": "error", "exit_code": 1, "error": man.get("error")}
        ff = _is_ancestor(git, main, dev)
        verdict = ("bless (default mode='ff') fast-forwards the whole dev tip; consent is "
                   "informational" if ff else
                   f"{main_branch} is not an ancestor of {dev_branch} — backmerge first")
        return {**base, **man, "status": "manifest", "exit_code": 0, "ff": ff,
                "message": f"{len(man['commits'])} rider(s) {main_branch}..{dev_branch}; "
                           f"{len(man['unapproved_riders'])} unapproved/unattributed; "
                           f"{len(man['dependencies'])} dependency conflict(s). {verdict}."}

    # ── BACKMERGE ── restore dev ⊇ main after a cut (merge commit, no checkout)
    if stage == "backmerge":
        from tools.noctus.dev._release_riders import backmerge_commit
        if _is_ancestor(git, main, dev):
            return {**base, "status": "up_to_date", "exit_code": 0,
                    "message": f"{dev_branch} already contains {main_branch}; nothing to backmerge."}
        bm = backmerge_commit(git, dev, main)
        if not bm["ok"]:
            return {**base, "status": "blocked", "exit_code": 1, "conflict": bm["detail"],
                    "reason": f"merging {main_branch} into {dev_branch} conflicts — resolve on a "
                              "feature branch (task_branch) and integrate; never force."}
        plan = {**base, "backmerge_sha": bm["sha"],
                "would_advance": f"{dev_branch} → {bm['sha'][:9]} (merge of {main_branch})"}
        if not confirm:
            return {**plan, "status": "planned", "exit_code": 0,
                    "message": "clean merge available. Pass confirm=True to push it to dev."}
        rc, out, err = git("push", remote, f"{bm['sha']}:refs/heads/{dev_branch}")
        if rc != 0:
            return {**plan, "status": "error", "exit_code": 1,
                    "error": f"push to {dev_branch} failed (dev moved? re-run): "
                             f"{err.strip() or out.strip()}"}
        new_dev = _resolve(git, f"{remote}/{dev_branch}")
        return {**plan, "status": "backmerged", "exit_code": 0, "new_dev_sha": new_dev,
                "verified": new_dev == bm["sha"]}

    # ── BLESS (dev → main) ──
    if stage == "bless":
        # REFUSE-NOT-NULL (2026-07-20): sha= previously SILENTLY IGNORED on
        # bless — the caller believed a pin took effect while bless still
        # advanced main to the dev TIP. Bless is a whole-repo-state concept
        # ("this dev-validated state") with no notion of a partial slice
        # (KB § PATTERNS/architect/git-branch-model.md); only promote pins.
        if sha:
            return {**base, "status": "error", "exit_code": 1,
                    "error": (
                        f"release: stage='bless' does not accept sha= (got {sha!r}). "
                        f"Bless always fast-forwards {main_branch} to the CURRENT "
                        f"{dev_branch} tip — there is no partial-bless concept "
                        "(KB § PATTERNS/architect/git-branch-model.md). If you meant to "
                        "pin a specific already-blessed commit for deployment, that is "
                        "promote's job: stage='promote' sha=<main-sha>. This refusal "
                        "replaces a prior SILENT no-op where sha= was accepted by the "
                        "schema but ignored by bless."
                    )}
        if dev == main:
            return {**base, "status": "up_to_date", "exit_code": 0,
                    "message": f"{main_branch} already == {dev_branch}; nothing to bless."}
        if release_branch:
            return _bless_release_branch(
                git, runner, base, manifest, remote, main, main_branch,
                release_branch, confirm)
        ff = _is_ancestor(git, main, dev)
        man = manifest()
        if not man.get("ok"):
            return {**base, "status": "blocked", "exit_code": 1,
                    "reason": f"cannot build the rider manifest: {man.get('error')} — "
                              "an unreadable manifest never buys a bless."}
        # Owner decision 2026-09-24: the owner's request to ship IS the
        # permission ("no approval needed when I ask — the ask is the
        # permission itself"). In the default mode='ff', per-project
        # ship-consent no longer gates bless; the manifest is an informational
        # record of whose work ships. mode='cut'/'refuse' remain as explicit
        # opt-ins for shipping only approved work. A first-ever prod exposure
        # of a NEW product is still gated separately (noctus.dev.prod_consent),
        # and CI-green still gates below.
        if mode == "ff":
            if not ff:
                return {**base, "status": "blocked", "exit_code": 1, "ff": False,
                        "reason": (f"{main_branch} is not an ancestor of {dev_branch} — "
                                   "run stage='backmerge' confirm=True first, then bless.")}
        elif not (man["all_approved"] and ff):
            return _bless_cut(git, base, man, mode, confirm, remote, main,
                              main_branch, dev_branch, ff, now)
        incoming = _commits(git, main, dev)
        # 🔴 CI-GREEN PRECONDITION (2026-08-22). noc-ship step 0b has always
        # called this MANDATORY, but nothing enforced it — so `1c83232f` was
        # blessed AND promoted to prod carrying a red `Tests & Build`, and dev
        # then stayed red for 12 commits with the gate reading as satisfied.
        # A doctrine-only gate is not a gate (CLAUDE.md §1, gate↔methodology
        # sync): the mechanism now ships with the rule.
        ci = _ci_verdict(runner, dev)
        docs_only = _is_docs_only(_changed_paths(git, main, dev))
        if ci["verdict"] != "green" and not docs_only:
            return {**base, "status": "blocked", "exit_code": 1, "ci": ci,
                    "incoming_commits": incoming,
                    "reason": (
                        f"CI is not green on the exact {dev_branch} tip {dev[:9]} "
                        f"(verdict={ci['verdict']}"
                        + (f", conclusion={ci['conclusion']}" if ci.get("conclusion") else "")
                        + f"): {ci.get('detail') or ci.get('url') or ''}. "
                        f"Bless requires a GREEN '{ci['workflow']}' "
                        f"on that sha — with the dev fleet dormant, CI is the only "
                        f"pre-prod functional evidence there is. Fix {dev_branch} and "
                        "re-run; the sole exception is a diff that is entirely docs/"
                        "project-history, which this diff is not."
                    )}
        plan = {**base, "would_advance": f"{main_branch} → {dev[:9]}", "incoming_commits": incoming,
                "ci": ci, "riders": {"all_approved": man["all_approved"], "commits": len(man["commits"]),
                                      "unapproved": man["unapproved_riders"]}}
        if docs_only and ci["verdict"] != "green":
            plan["ci_exception"] = ("docs-only diff (no executable path changed) — "
                                    "noc-ship step 0b's sole sanctioned CI exception")
        if not confirm:
            return {**plan, "status": "planned", "exit_code": 0,
                    "message": f"clean FF available: bless {len(incoming)} commit(s) "
                               f"{main_branch} → {dev_branch}. Pass confirm=True to push."}
        # ACT — the sanctioned override push (FF; hook still blocks force/delete)
        rc, out, err = git("push", remote, f"{dev}:refs/heads/{main_branch}",
                           env_extra={"NOCTUS_ALLOW_MAIN_PUSH": "1"})
        if rc != 0:
            return {**plan, "status": "error", "exit_code": 1,
                    "error": f"push to {main_branch} failed: {err.strip() or out.strip()}"}
        new_main = _resolve(git, f"{remote}/{main_branch}")
        return {**plan, "status": "blessed", "exit_code": 0, "new_main_sha": new_main,
                "verified": new_main == dev,
                "message": f"blessed {len(incoming)} commit(s) to {main_branch}. "
                           f"To deploy: noctus.dev.release stage='promote' (ships ALL of "
                           f"{prod_branch}..{main_branch} — review first)."}

    # ── PROMOTE (main → prod, snapshot prod → prod-backup first) ──
    target = None
    if sha:
        target = _resolve(git, sha)
        if not target:
            return {**base, "status": "error", "exit_code": 1,
                    "error": f"cannot resolve sha '{sha}'."}
        if not _is_ancestor(git, target, main):
            return {**base, "status": "blocked", "exit_code": 1,
                    "reason": f"sha {target[:9]} is not contained in {main_branch} — only a "
                              f"blessed {main_branch} sha may be promoted."}
    else:
        target = main
    if not prod:
        return {**base, "status": "error", "exit_code": 1,
                "error": f"cannot resolve {remote}/{prod_branch}."}
    if prod == target:
        return {**base, "status": "up_to_date", "exit_code": 0, "target_sha": target,
                "message": f"{prod_branch} already == target; nothing to promote."}
    if not _is_ancestor(git, prod, target):
        return {**base, "status": "blocked", "exit_code": 1, "target_sha": target,
                "reason": f"{prod_branch} is not an ancestor of the target — not a clean FF. "
                          "Diagnose, do not force."}
    # prod-backup must be able to FF to the *current* prod (we snapshot it there).
    backup_ff = (backup is None) or _is_ancestor(git, backup, prod)
    if not backup_ff:
        return {**base, "status": "blocked", "exit_code": 1, "target_sha": target,
                "reason": f"{backup_branch} ({backup[:9] if backup else '∅'}) is not an ancestor "
                          f"of {prod_branch} ({prod[:9]}) — snapshot would not be a clean FF. "
                          "Realign prod-backup deliberately first."}
    incoming = _commits(git, prod, target)
    _rc, diff_out, _e = git("diff", "--name-only", f"{prod}..{target}")
    changed_files = [ln.strip() for ln in diff_out.splitlines() if ln.strip()]
    rebuild = _rebuild_decision(changed_files)

    plan = {
        **base, "target_sha": target, "incoming_commits": incoming,
        "snapshot": f"{backup_branch} → {prod[:9]} (current prod, pre-promote)",
        "would_advance": f"{prod_branch} → {target[:9]}",
        "large_promote": len(incoming) > 10,  # loud flag — promoting a big backlog
        "rebuild": rebuild,
    }
    if not confirm:
        return {**plan, "status": "planned", "exit_code": 0,
                "message": (f"clean FF available: snapshot {backup_branch}←prod, then promote "
                            f"{len(incoming)} commit(s) {main_branch}→{prod_branch}. "
                            + ("⚠ LARGE promote — review the commit list. " if len(incoming) > 10 else "")
                            + "Pass confirm=True. After: noctus.dev.deploy_pull confirm=True.")}
    # ACT 1 — snapshot current prod onto prod-backup (FF; not a protected branch)
    rc, out, err = git("push", remote, f"{prod}:refs/heads/{backup_branch}")
    if rc != 0:
        return {**plan, "status": "error", "exit_code": 1,
                "error": f"prod-backup snapshot push failed: {err.strip() or out.strip()}"}
    # ACT 2 — promote (the sanctioned override push; FF only)
    rc, out, err = git("push", remote, f"{target}:refs/heads/{prod_branch}",
                       env_extra={"NOCTUS_ALLOW_MAIN_PUSH": "1"})
    if rc != 0:
        return {**plan, "status": "error", "exit_code": 1,
                "snapshot_done": True,
                "error": f"promote push to {prod_branch} failed: {err.strip() or out.strip()}"}
    new_prod = _resolve(git, f"{remote}/{prod_branch}")
    new_backup = _resolve(git, f"{remote}/{backup_branch}")
    return {**plan, "status": "promoted", "exit_code": 0,
            "new_prod_sha": new_prod, "new_backup_sha": new_backup,
            "verified": new_prod == target and new_backup == prod,
            "message": (f"promoted {len(incoming)} commit(s) to {prod_branch}; "
                        f"{backup_branch} now holds the previous prod ({prod[:9]}). "
                        "Deploy to the VPS: noctus.dev.deploy_pull confirm=True"
                        + (f" (rebuild: {', '.join(rebuild['products']) or 'fleet'})"
                           if rebuild.get("needed") else " (no rebuild — non-runtime).")) }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.release",
        description=(
            "Run the release/deploy gates for the sacred-main branch "
            "model (KB § PATTERNS/branching-and-merging.md § 0.2). stage='status' "
            "(default) shows the feat→dev→main→prod chain (SHAs, FF-ability, the "
            "commits each hop would ship) read-only; stage='bless' fast-forwards "
            "main to the dev tip (sha= is NOT accepted here — REFUSED loudly, not "
            "silently ignored: bless is a whole-repo-state concept, no partial slice); "
            "stage='promote' snapshots the current prod onto prod-backup then "
            "fast-forwards prod to a blessed main sha (pass sha= to pin; default = "
            "main tip — which ships ALL of prod..main, flagged large_promote). "
            "OWNER DECISION 2026-09-24: the owner's request to ship IS the "
            "permission — default mode='ff' fast-forwards main to the WHOLE dev tip "
            "with no per-project ship-consent check (CI green on that exact sha is "
            "still required; a diverged main is refused until stage='backmerge'). "
            "stage='manifest' (read-only) lists every commit main..dev grouped by "
            "project with its (now informational) ship-consent state. Opt-in "
            "mode='cut' builds release/<YYYYMMDD-HHMM> = main + approved commits "
            "only, then bless release_branch=<name> confirm=True FFs main to it once "
            "CI is green on its exact sha; mode='refuse' blocks on unapproved work. "
            "A NEW product's first prod exposure stays gated by noctus.dev.prod_consent. "
            "stage='backmerge' merges main into dev (merge commit) so dev ⊇ main. "
            "DRY-RUN by default — pass confirm=True to push. FF-only "
            "by construction (never force/reset/checkout). It is the ONLY sanctioned "
            "setter of NOCTUS_ALLOW_MAIN_PUSH, and only for its own push. After a "
            "promote, run noctus.dev.deploy_pull to pull origin/prod onto the VPS. "
            "TOOLKIT-STALENESS GUARD (2026-09-18): a confirm=True call (the "
            "one that actually pushes main/prod) REFUSES (status="
            "'refused_stale_toolkit', exit_code=1) when this MCP server's own "
            "module graph has drifted from disk since it was imported; a "
            "confirm=False status/plan call is only warned. "
            "allow_stale_toolkit=True is the escape hatch (almost always "
            "wrong). See noctus.dev.toolkit_freshness. "
            "status: status|manifest|planned|planned_cut|cut_pushed|up_to_date|"
            "blocked|blessed|promoted|backmerged|error|refused_stale_toolkit."
        ),
    )
    def _release(
        stage: str = "status",
        confirm: bool = False,
        sha: str | None = None,
        mode: str = "ff",
        release_branch: str | None = None,
        allow_stale_toolkit: bool = False,
    ) -> dict:
        return release(stage=stage, confirm=confirm, sha=sha, mode=mode,
                       release_branch=release_branch,
                       allow_stale_toolkit=allow_stale_toolkit)


__all__ = ["release", "_ALLOWED_GIT", "_BANNED_TOKENS", "register"]
