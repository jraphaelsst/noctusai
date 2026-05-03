# CLAUDE/platform.md — cross-cutting platform rules

> **Loading discipline.** This file is not auto-loaded. Read it when touching cross-cutting concerns: MCP toolkit, MCP server design, LGPD-sensitive data, root-folder hygiene, shared library, KB depth itself. The §3 routing table in `CLAUDE.md` is the canonical signal. Sibling of `CLAUDE.md`, NOT depth (depth lives in `KNOWLEDGE-BASE/`).

## Rules

- **MCP toolkit reviews after every change (observation-only).** `python mcp/noctusai/cli.py --review` after modifying code. Detects compliance issues deterministically; LLM (OpenAI, `OPENAI_API_KEY`) authors a proposal per issue. Keeper proposals → `products/<product>/proposals/`. Project-scoped proposals → the project's own `proposals/` folder. **The tool NEVER modifies code.** Loop: change → review → triage → apply manually → commit. (Old auto-fix `--heal` retired — text rewrites corrupt code, string-match checks rot.) → `KB § 06-AGENTS.md`
- **MCP-first — agent-exposable capabilities default to MCP.** When you want to expose a capability to agents (Claude Code, future bots, future product agents), the default surface is the MCP server at `mcp/noctusai/`. Dev tooling, business-logic primitives, vendor adapters all converge there as one growing wide-purpose toolkit. Naming: 3-segment dotted (`<umbrella>.<service>.<action>`). Pattern: Pydantic in/out schemas, hierarchical registration, lazy `NoctusContext` for business-logic tools. Composition belongs to the consumer. Boundary: if a capability has only one co-located consumer, a plain function is fine; MCP-first fires when a plausible second consumer exists. → `KB § 01-PHILOSOPHY.md § MCP-first`
- **Clean folder — every artifact has a home.** Repo root holds only platform-wide files (CLAUDE.md, README.md, docker-compose.yml, .gitignore, scripts pointer, plus the `CLAUDE/` topical-rules directory). Audits / proposal drafts / design notes / scratch `.md` files belong inside a project folder as first-class reference artifacts quoted by `PROJECT.md §1/§5`. Stray root file → scaffold the project, move the file in, inline load-bearing bits into PROJECT.md, delete root copy. Prefer ONE umbrella project over N scattered one-finding folders. → `KB § PATTERNS/project-execution.md § 11 Clean-folder principle`
- **LGPD-first, always.** Whenever code touches personal data (identity, financial, clinical, behavioral, derived embeddings, …), the LGPD lens is the **first** lens — before functionality, performance, UX. Clinical text is Art. 11 sensitive data; never leaves Therapy schema without a documented basis, never hits a response cache. When in doubt: `noctus.dev.lgpd_flag(...)` — records to `LGPD-WARNINGS.md`, notifies the user, **does not block**. The flag is a checklist item, ticked when resolved. → `KB § PATTERNS/lgpd.md`

## Pointers (depth)

- MCP dev toolkit (review loop, proposals, CLI) → `KB § 06-AGENTS.md`
- MCP server design (3-segment naming, Pydantic, NoctusContext) → `KB § INSTRUCTIONS/02-MCP.md`
- Shared-library catalog → `KB § 04-SHARED-LIBRARY.md`
- Seed-lib layout (6 layers — primitives/config/testing/integrations/domain/api) → `KB § PATTERNS/seed-lib-layout.md`
- LGPD awareness (keeper principle, the five questions, `noctus.dev.lgpd_flag` tool) → `KB § PATTERNS/lgpd.md`
- AST-driven code edits (libcst / ts-morph / tree-sitter) → `KB § PATTERNS/ast.md`
- Agent reading & research discipline → `KB § PATTERNS/agent-reading-discipline.md`
