# GitHub connector MCP — `mcp/github`

> The **GitHub side of the team methodology** exposed as LLM-callable
> tools: PR lifecycle + CI-check visibility + repo introspection. Wraps
> the operator's authenticated `gh` CLI. Composes `mcp/_kit` (same shape
> as vista/meta/google). Built 2026-05-18.

## Why it exists

Methodology improvement target: the **commit → push → PR → review → CI**
loop. The commit/push half is already governed (commit-only-your-own-work
∧ engineers-stage-architect-commits, CLAUDE.md §1) — exposing raw `git
commit`/`git push` as tools would let any agent bypass authorship
discipline. So this connector covers the **GitHub-platform half** (PRs /
checks / repo state) *after* commits land via the normal git workflow.
Scope boundary is deliberate, not an omission.

## Tool surface (`github.<service>.<action>`, 3-segment dotted)

| Tool | Kind | `gh` wrapped |
|---|---|---|
| `github.pr.list` | READ | `gh pr list --json` |
| `github.pr.view` | READ | `gh pr view --json` |
| `github.pr.diff` | READ | `gh pr diff` |
| `github.pr.checks` | READ | `gh pr checks --json` (merge-readiness) |
| `github.pr.create` | WRITE 🔒 confirm | `gh pr create` |
| `github.pr.ready` | WRITE 🔒 confirm | `gh pr ready` |
| `github.repo.view` | READ | `gh repo view --json` |
| `github.diagnostics.connection_status` | READ | `gh --version` ∧ `gh api user` |

- Writes: confirm-then-execute (`KB § PATTERNS/security/llm-bot-security.md`).
  `confirm` ≠ true ⇒ typed error `status 412`, ¬ side-effect.
- `github.pr.checks` uses the runner's `allow_nonzero` opt-in — `gh pr
  checks` encodes CI *state* (exit 8 pending / 1 failing) in the exit
  code with valid JSON on stdout; empty stdout still ⇒ error.

## Architecture

- Composes `_kit`: `prepare_sys_path` (PyPI-`mcp`-shadow + in-tree seed
  pin) · `make_get_settings` · `build_registry` · `typed_error` ·
  `run_stdio_server`. ~0 boilerplate re-derived. `github` imports as a
  top-level package (no flat-`sys.path[0]` collision — `types.py` safe).
- **Single external seam:** `github.gh.run_gh` (subprocess). Tests
  `unittest.mock.patch` it — `gh`/GitHub is an external service
  (CLAUDE.md §1 sanctioned class); our own code is never patched.
- **Gated-capability honesty:** `gh` absent / logged-out ⇒ typed
  never-faked signal (read tools → `status 424`; diagnostics →
  `gh_available=false` / `authenticated=false`). Server boots clean with
  no config (deferred-config rule); never fabricates a success.

## Config (`mcp/github/.env` ∨ env)

| Var | Meaning | Default |
|---|---|---|
| `GITHUB_DEFAULT_REPO` | `OWNER/REPO` target | `gh` infers from cwd remote |
| `GITHUB_GH_PATH` | `gh` binary override | `gh` on `PATH` |

No secret here — `gh auth login` owns the token (keyring). `timeout_seconds`
is a pure dataclass default (off `env_map`, vista's rule).

## Registration — USER-GATED

`.mcp.json` add is **opt-in** per the MCP keep-list rule (CLAUDE.md §1 —
standing allowlist = `noctusai` + `supabase`; every other server needs
explicit user approval):

```json
"github": { "command": "mcp/github/.venv/bin/python",
            "args": ["mcp/github/server.py"], "cwd": "<repo root>" }
```

Prereq: `gh` installed ∧ `gh auth login` run by the operator.

## Tests

`cd mcp && python -m pytest github/tests/ -q` — 15 tests, no network.
Pins: tool-name set · dotted naming · confirm-gate (¬ side-effect) ·
gated-capability honesty (424, never faked) · registry coherence.

## Provenance

Built 2026-05-18 off `origin/main` as branch `github-mcp-connector`.
Connector #4 composing `mcp/_kit` (vista/meta/google precede). First
connector wrapping a **CLI** (not a `noctusai_lib.integrations.<vendor>`
adapter) — the kit's generic plumbing carried it unchanged; only the
external seam shape differs (subprocess vs HTTP adapter).
