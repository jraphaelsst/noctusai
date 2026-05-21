# OPENAI.md · v1.0

> **What this file is.** OpenAI agents' **outer map** for this repository. It establishes the high-level behavioral rules to follow every session and points into `KNOWLEDGE-BASE/` for the authoritative technical and architectural depth.
>
> **What this file is NOT.** A second source of truth, a parallel spec, or a long-form architecture manual. Shared doctrine lives in `KNOWLEDGE-BASE/`. If a rule needs a paragraph, examples, or historical context, document it in the KB and keep this file as a short pointer.
>
> **DRY across model families.** `OPENAI.md` and `CLAUDE.md` are sibling outer maps for different model families. They should stay aligned at the principle level and both point to the same KB sources. Future instruction changes land in the KB first, then the short pointer text in both root files is updated.
>
> When you can't find something, open **`KNOWLEDGE-BASE/INDEX.md`** first.

## 1 · First Rules

- **Seed is the skeleton. First rule.** `seed/` owns the structural bones of the platform; products are organs that attach to that skeleton through runtime imports, not copy-paste. Backend uses `create_product_app()` from `noctusai_seed`; frontend uses `createProductApp()` from `@noctusai/seed`. If a structural fix requires editing multiple products manually, the skeleton model is drifting. Read `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md § Seed as Skeleton` and `§ Seed Contract`.
- **KB-first, outer-map second.** When a rule, pattern, or doctrine changes, update the relevant KB file first, then sync the short pointer in `OPENAI.md` and `CLAUDE.md`. Do not let model-specific root files become competing sources of truth. Read `CLAUDE.md § Docs stay in sync` and `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`.
- **No quick fixes.** If the same structural fix belongs in multiple products, the fix probably belongs in `seed`, a shared library, or a shared config. Read `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md § No quick fixes`.
- **DRY.** Three similar blocks is a pattern. Extract it. Keep one authoritative source for code, config, and doctrine. Read `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md § DRY`.
- **No silent errors.** If a tool fails, a test is red, a claim is unverified, or an assumption was necessary, surface it explicitly. Read `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md § No silent errors`.

## 2 · Where To Read Next

Open only what the current task needs.

- **Platform philosophy / behavior rules** → `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`
- **Product landscape** → `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md`
- **Seed architecture / seed contract / skeleton doctrine** → `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md`
- **Shared library catalog** → `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md`
- **Infrastructure** → `KNOWLEDGE-BASE/CONTEXT/05-INFRASTRUCTURE.md`
- **MCP toolkit / review flow / proposal flow** → `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`
- **Backend conventions** → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend.md`
- **Frontend conventions** → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/frontend.md`
- **Testing** → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/testing.md`
- **Database / RLS** → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md`
- **Environment / `.env`** → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/environment.md`
- **Project execution** → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md`
- **Proposals and improvements** → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md`
- **Creating a new product** → `KNOWLEDGE-BASE/CONTEXT/GUIDES/new-product.md`
- **Production deploy of the fleet to a VPS** (git deploy-key → build-on-VPS → `noctus-net` → Caddy-on-real-subdomains or CF named tunnel; volume-preserving PaaS decommission; LE/compose/cloudflared/OpenAI-LLM lessons) → `KNOWLEDGE-BASE/CONTEXT/GUIDES/production-deploy.md`

## 3 · Documentation Workflow

When future OpenAI agents need to document or update instructions:

1. Decide whether the content is a deep rule, technical pattern, architecture doctrine, or procedural guide.
2. Write or update the authoritative content in `KNOWLEDGE-BASE/`.
3. Update `KNOWLEDGE-BASE/INDEX.md` if a new KB file is added or renamed.
4. Only then update the short pointer text in `OPENAI.md`.
5. If the principle is shared across model families, sync the matching short pointer in `CLAUDE.md` too.

Use this split consistently:

- `KNOWLEDGE-BASE/` = authoritative depth
- `OPENAI.md` = OpenAI-facing outer map
- `CLAUDE.md` = Claude-facing outer map

Do not create a separate OpenAI-only doctrine if the rule is actually platform-wide.

## 4 · Practical Decision Test

Before proposing or implementing a structural change, ask:

- Is this a bone or an organ?
- If it is a bone, why is it not in `seed` yet?
- If it is an organ, is it truly domain-specific or just duplicated structure wearing domain clothes?
- Will changing `seed` propagate this to every wired product automatically?

If the answer to the last question is no, investigate whether the architecture is drifting away from the seed-skeleton model.
