---
name: skill-creator
description: Use when authoring or vendoring a Claude Code skill for noc — triggers "create a skill", "write a skill", "new skill", "make a skill for X", "vendor this skill in-home". Encodes the noc skill conventions + the bring-in-home (never-depend) protocol.
version: 1.0.0
---

# skill-creator — author/vendor noc skills the right way

A skill = `.claude/skills/<name>/SKILL.md`: frontmatter (`name` + `description`, optional `version`) always-loaded, body loaded on trigger. The description is the router — pack it with the literal trigger phrases a user/agent would say.

## Authoring conventions (noc)

1. **Name = `noc-<verb-noun>`** for platform workflows (instantly spottable, clusters under `noc-`). Non-noc-specific meta-skills keep a plain name.
2. **Description = what + when, third person, with trigger phrases** verbatim in quotes — house form: "Use when … — triggers '…', '…'." (≤1024 chars; the spec + best-practices bar is in `KB § PATTERNS/common/vendored-skills.md` §5).
3. **Body = a thin WORKFLOW**, not a doc: numbered steps + which MCP tools to call in sequence + a `## Guardrails` + a `

- **Open findings are injected by the harness hook** (`claude-inject-open-findings.py`), so a skill/agent needs no findings line; a skill that owns a loop registers its ledger with `noctus.dev.findings_ledger action=scaffold`. → `KB § PATTERNS/common/living-findings-ledgers.md`

## Depth` pointer to the KB home.
4. **Never restate KB.** The skill carries the *procedure*; KB carries the *depth*. A skill that copy-pastes a KB body is a new drift generator — point, don't copy (`→ KB § …`).
5. **DRY on creation (user mandate):** when a procedure moves INTO a skill, DELETE it from its old home (CLAUDE.md §2/§3 routing rows, duplicated memory). Re-home, don't duplicate.
6. **Register intent:** new noc skills expand the CLAUDE.md skills keep-list — note it (a methodology decision), don't silently add.

## Vendoring an external skill (bring-in-home, never depend)

1. **Find** via the curated hunting grounds (see `skill-scout` agent): `anthropics/skills`, `travisvn/awesome-claude-skills`, `ComposioHQ/awesome-claude-skills`, `VoltAgent/awesome-agent-skills`, `GetBindu/awesome-claude-code-and-skills`.
2. **Vet the CONTENT, then the LICENSE** (content checklist + SPDX decision table: `KB § PATTERNS/common/vendored-skills.md` §3–§4). Permissive (MIT/BSD/Apache-2.0 + NOTICE) → copy + adapt. Source-available (e.g. Anthropic document skills), copyleft, no license or unclear → DO NOT copy; author an in-home equivalent from the public format knowledge + surface the license reason.
3. **Copy in-home** under `.claude/skills/<name>/` — NEVER `/plugin install`, never wire to a marketplace, never add a runtime dependency. Strip external coupling (plugin-root paths, vendor MCP assumptions).
4. **Adapt to noc** — rename to convention, point `## Depth` at our KB, add a provenance line (source URL + license + date).
5. **Record provenance** in the vendored-skill register, `KB § PATTERNS/common/vendored-skills.md` §6a, same commit, so the copy's origin survives.

## Depth
Format spec: https://agentskills.io/specification (+ Anthropic best practices, summarised in `KB § PATTERNS/common/vendored-skills.md` §5) · noc home for this practice: `KB § PATTERNS/` (the skill being authored points to its own depth doc).
