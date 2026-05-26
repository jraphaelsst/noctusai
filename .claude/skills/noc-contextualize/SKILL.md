---
name: noc-contextualize
description: Use when a fresh/clean-context agent needs orientation on the NoctusAI platform — triggers "contextualize", "please contextualize", or genuine "I don't know what this platform is". One read, then oriented. Skip if already working/oriented.
version: 1.0.0
---

# noc-contextualize — fresh-agent onboarding ramp

If you are already working / already oriented, this is a NO-OP — skip it (re-reading wastes tokens).

## Workflow

1. Read `/CONTEXTUALIZE.md` (repo root) top-to-bottom — it is the curated read-map (mental model + the core read order), not a copy of the docs.
2. Follow its core set in order: `CLAUDE.md` §1 → `KB § AGENT-CONTEXT.md` → `KB § CONTEXT/02-LANDSCAPE.md` → `KB § CONTEXT/01-PHILOSOPHY.md` → `KB § CONTEXT/03-SEED-ARCHITECTURE.md` → `KB § INDEX.md` → `MEMORY.md`. Stop when you have enough for the task; the rest is on-demand.
3. Hold the mental model before touching anything: seed-first · living/self-improving methodology · three-way sync · codebase is source of truth · no silent errors · branching-first · AST-first · fix-on-contact.

## Guardrails
- Do NOT pre-read everything — the methodology values lean context; pull depth on-demand via `CLAUDE.md` §2/§3 + `KB § INDEX.md`.
- After material changes to the core onboarding docs, re-run the clean-context self-test.

## Depth
`/CONTEXTUALIZE.md` · `CLAUDE.md` §1 (the behavioral contract).
