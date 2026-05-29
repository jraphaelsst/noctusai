# Versioning — SemVer with explicit pre-release stages

**What it is.** A formal versioning scheme for the noc methodology + platform. SemVer-based (`MAJOR.MINOR.PATCH[-PRERELEASE]`) with explicit pre-release stages (`alpha` / `beta` / `rc`). Born 2026-05-26 with the v4.0-beta release after the dev-team + structural refactor work.

## The scheme: `MAJOR.MINOR.PATCH[-PRERELEASE]`

Standard [Semantic Versioning](https://semver.org/) with project-specific semantics:

| Component | When to bump | Examples |
|---|---|---|
| **MAJOR** (4.x.x → 5.x.x) | Breaking structural refactor — methodology surface count changes, agent context architecture overhaul, file-tree reorg | Adding the dev-team specialist agents (3.x → 4.0); rewriting the seed lib layout |
| **MINOR** (4.0.x → 4.1.x) | Backward-compatible new functionality — new keeper, new MCP tool, new methodology rule | Adding `check_eight_way_sync` keeper; new `vector_calibration` module |
| **PATCH** (4.0.0 → 4.0.1) | Backward-compatible fix — bug fix, doc-only update, small refinement of existing rule | Fixing the kb_sync adapter; trimming MEMORY.md entries |
| **PRERELEASE** (`-alpha` / `-beta` / `-rc`) | Stability stage marker on top of MAJOR/MINOR/PATCH | `4.0.0-beta` → `4.0.0-rc1` → `4.0.0` |

The user's intuition — *"4.0 → 4.0.1 → 4.1 → 4.1.1, shape depends on hierarchy depth"* — matches SemVer exactly: PATCH is leaf-depth (small fix on the current MINOR), MINOR is branch-depth (new feature on current MAJOR), MAJOR is trunk-depth (structural change).

## Pre-release stages (and a noc-specific note)

**Standard SemVer convention** (PEP 440, npm, GitHub releases all agree):

```
alpha   →   beta   →   rc   →   release
(less stable)               (more stable)
```

- **alpha**: earliest preview. Features incomplete, API may change drastically. Internal-only by default.
- **beta**: feature-complete; testing for bugs + refinement. External preview OK with warnings.
- **rc** (release candidate): code-frozen; only critical fixes between rc-N and final.
- **release** (no suffix): the final stable version.

**Note on noc's 2026-05-26 release flow**: the v4.0 cycle is using these terms in their **standard order** going forward (alpha < beta). Earlier conversation referred to "alpha when tested" — that was a flipped meaning. The codified contract here uses the convention: `alpha → beta → rc → release`.

## What "version" means for noc specifically

This isn't a library that other code imports — noc is a methodology + platform. The version stamp tracks:

1. **Methodology surface contract** (the 8-way sync state).
2. **Keeper / compliance.py rules** (what's enforced as Stage-4).
3. **MCP tool surface** (the noctus.dev.* + noctus.vps.* + noctus.seed.* fleet).
4. **Agent + skill + command roster**.
5. **KB pattern doc count + structure**.

A MAJOR bump means at least one of these had a non-back-compat restructuring (file moves, rule renames, agent contracts changing). The v3 → v4 jump bundled the dev-team agent roster + the PATTERNS reorg + the 6→7-way sync evolution.

## Where the version lives

| File | What it carries |
|---|---|
| **`/VERSION`** | Single source of truth. Plain text, one line: `<MAJOR>.<MINOR>.<PATCH>[-<PRERELEASE>]\n`. Committed; read by tooling. |
| **`seed/{lib,framework}/backend/.../_version_static.py`** | Auto-stamped per commit by `noctus.dev.stamp_seed_version` (pre-commit hook step 3). Carries `__version__` (git short SHA — `check_seed_version_propagation` keeper contract) AND `__semver__` (the SemVer from `/VERSION` — readable as `noctusai_seed.__semver__` / `noctusai_lib.__semver__`). Gitignored. |
| **Git tags** | `vX.Y.Z[-PRERELEASE]` (e.g. `v4.0.0-beta`). Created per release. `git tag -a vX.Y.Z -m "release notes"` then `git push origin vX.Y.Z`. |
| **`/CHANGELOG.md`** | Human-readable release notes per version. Each entry: version, date, summary, breaking changes (if any), new features, fixes. |
| **Pre-commit hook** | Echoes the current `VERSION` so every commit-time agent sees the stamp. Also gates MAJOR bumps via `--check-version-bump`. |

## Authorization gate (the *.0 ramp is the human's)

**The architect/agent autonomously authors PATCH and MINOR bumps. MAJOR bumps require explicit human authorization.**

This is enforced structurally via `noctus.dev.version_guard` (CLI: `--check-version-bump`), wired into the pre-commit hook as step 3a. Behavior:

| Bump shape | Gate verdict | Required action |
|---|---|---|
| VERSION unchanged | `no_change` ✓ | — |
| `4.0.0 → 4.0.1` (PATCH within MAJOR) | `minor_or_patch` ✓ | None — autonomous |
| `4.0.0 → 4.1.0` (MINOR within MAJOR) | `minor_or_patch` ✓ | None — autonomous |
| `4.x.y → 5.0.0` (MAJOR ramp) | `major_unauthorized` ✗ BLOCKS | Create `.major-bump-authorized` at repo root with a one-line rationale, stage it WITH the VERSION bump in the same commit; gate flips to `major_authorized` ✓ |

The marker is git-tracked so the authorization is visible in history; the same commit that bumps MAJOR should also remove the marker (so a stale marker can't re-arm a future un-authorized bump). The gate runs only when `VERSION` is staged.

Why a file-based marker and not a commit-message trailer: pre-commit fires BEFORE the commit message is finalized, so a trailer-based check would need a second hook (`commit-msg`) and risks bypass via `--no-verify`. A staged-file marker is checkable at pre-commit time AND visible in the audit trail.

## How to bump

1. **Decide the bump level** — open `VERSION`, decide MAJOR / MINOR / PATCH based on the table above.
2. **Update `VERSION`** (single line, no prose).
3. **Append to `CHANGELOG.md`** — version + date + summary + breaking-changes + features + fixes.
4. **Tag the commit** — `git tag -a vX.Y.Z -m "<one-line summary>"` then `git push origin vX.Y.Z`.
5. **Update CLAUDE.md** if the version is referenced in a §1 rule or §2 listing (e.g. a "v4.0 synthesis" marker in the router preamble).

## Conventional Commits integration

The repo already follows [Conventional Commits](https://www.conventionalcommits.org/) — commit messages use prefixes `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`. These MAP to SemVer bumps:

| Commit prefix | SemVer effect |
|---|---|
| `feat:` | MINOR bump (unless `BREAKING CHANGE:` footer → MAJOR) |
| `fix:` | PATCH bump |
| `chore:` / `docs:` / `refactor:` | usually no bump (unless behavior-visible — judgment) |
| Footer `BREAKING CHANGE: <why>` | MAJOR bump regardless of prefix |

The bump itself stays manual (in `VERSION`) so a human decides — Conventional Commits suggests the level, doesn't dictate.

## Anti-patterns

- **DON'T** skip a version stamp on a methodology-surface change. The version IS the methodology contract version; silent surface changes ⇒ external consumers can't tell what they're getting.
- **DON'T** bump MAJOR for a feature add. Methodology growth is MINOR; structural rewrites are MAJOR.
- **DON'T** invent new pre-release stage names. Stick to `alpha / beta / rc / (none)`.
- **DON'T** rewrite a published tag — append a new one. Tags are immutable.

## Composes with

- [`eight-way-sync`](eight-way-sync.md) — the methodology surface contract this version stamps.
- [`claude-md-router-discipline`](claude-md-router-discipline.md) — versioned content sits inside CLAUDE.md too.
- [`roadmap-tracking`](roadmap-tracking.md) — roadmaps occupy a version slice; multi-version roadmaps explicit about which version each slice ships under.
- Conventional Commits (external standard) — the commit-message contract the bump scheme rides on.

## History

- v3.x: pre-dev-team era (no formal versioning). Methodology lived in CLAUDE.md without a stamp.
- v4.0.0-beta (2026-05-26): first formal version stamp. Marks the dev-team + structural refactor + 7-way sync state. Tagged `v4.0.0-beta` after the doc-sprint commit cluster.
- (planned) v4.0.0-rc1: after next-session validation + refinement.
- (planned) v4.0.0: final stable.
