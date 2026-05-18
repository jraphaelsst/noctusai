"""`mcp/github` — GitHub connector MCP (methodology surface).

A connector-MCP server (composes `mcp/_kit`, same shape as
`mcp/vista` / `mcp/meta` / `mcp/google`) that exposes the **GitHub
platform facilities the team's methodology relies on** — PR lifecycle,
CI-check visibility, repo/branch introspection — as LLM-callable
`github.<service>.<action>` tools.

It wraps the operator's **authenticated `gh` CLI** (no PyGithub, no token
handling — `gh auth` owns credentials). Raw `git commit` / `git push`
are deliberately NOT exposed: those stay in the established git +
commit-only-your-own-work authorship workflow (CLAUDE.md §1). This
connector is the *GitHub side* of that methodology (PRs / checks / repo),
not a git wrapper. See `mcp/github/README.md`.
"""
