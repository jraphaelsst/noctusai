# `mcp/github` — GitHub connector MCP (methodology surface)

## What this is

A connector-MCP server that exposes the **GitHub platform facilities the
team's methodology relies on** — PR lifecycle, CI-check visibility,
repo/branch introspection — as LLM-callable `github.<service>.<action>`
tools. It **composes `mcp/_kit`** (same shape as `mcp/vista` /
`mcp/meta` / `mcp/google`): bootstrap, settings, registry, error
envelope, in-tree seed pin — all inherited, ~0 boilerplate re-derived.

It wraps the operator's **authenticated `gh` CLI** (`gh auth` owns
credentials — no PyGithub, no token handling here).

## Why commit / push are NOT exposed (scope boundary)

The methodology rule **commit + push only your own work** + the
engineers-stage-architect-commits split (CLAUDE.md §1, `.claude/agents/
engineer-seed.md §2`) deliberately keeps raw `git commit` / `git
push` in the human-audited git workflow. Exposing them as MCP tools
would let any agent turn round-trips into commits, defeating authorship
discipline. This connector is the **GitHub side** of the methodology —
PRs, checks, repo state — *after* commits already landed via the normal
workflow. It improves the **PR / review / CI** loop, not the commit loop.

## Tool surface

| Tool | Kind | Wraps |
|---|---|---|
| `github.pr.list` | READ | `gh pr list --json` |
| `github.pr.view` | READ | `gh pr view --json` |
| `github.pr.diff` | READ | `gh pr diff` |
| `github.pr.checks` | READ | `gh pr checks --json` (merge-readiness signal) |
| `github.pr.create` | WRITE — confirm-gated (412) | `gh pr create` |
| `github.pr.ready` | WRITE — confirm-gated (412) | `gh pr ready` |
| `github.repo.view` | READ | `gh repo view --json` |
| `github.diagnostics.connection_status` | READ | `gh --version` + `gh api user` |

Writes follow the **confirm-then-execute** gate (`KB §
PATTERNS/llm-bot-security.md`): `confirm` omitted/false ⇒ typed error
`status 412`, **NO side-effect**. PR bodies are sent verbatim to GitHub
(human-read) — author them as prose, never symbol-first (doc-symbology
§3 NOT-list).

## Gated-capability honesty

`gh` absent or logged-out is a **typed, never-faked** signal
(CLAUDE.md §1): read tools return a `GitHubCliError` envelope
(`status 424`), `github.diagnostics.connection_status` reports
`gh_available=false` / `authenticated=false`. The server boots cleanly
with no config (deferred-config rule) and never fabricates a success.

## Config (`mcp/github/.env` or env)

| Var | Meaning | Default |
|---|---|---|
| `GITHUB_DEFAULT_REPO` | `OWNER/REPO` target | `gh` infers from cwd remote |
| `GITHUB_GH_PATH` | `gh` binary override | `gh` on `PATH` |

No secret lives here — `gh auth login` owns the token (keyring).

## Registration (user-gated)

Add to `.mcp.json` under `mcpServers` **only with explicit user
approval** (MCP keep-list rule, CLAUDE.md §1 — `noctusai` + `supabase`
are the standing allowlist; every other server is opt-in):

```json
"github": {
  "command": "mcp/github/.venv/bin/python",
  "args": ["mcp/github/server.py"],
  "cwd": "<repo root>"
}
```

(`gh` itself must be installed + `gh auth login` run by the operator.)

## Tests

```
cd mcp && python -m pytest github/tests/ -q
```

No network — pure validation (confirm gate) or `unittest.mock.patch` on
the external `gh` seam (`github.gh.run_gh` / `github.gh.gh_available`).
Pins the tool-name set, dotted naming, the confirm gate (no side-effect),
gated-capability honesty, and registry coherence.
