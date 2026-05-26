# Lenses-applied commit trailer — making inline-empersonation auditable

**What it is.** A lightweight commit-trailer convention (`Lenses: <name>[, <name>...]`) that records which specialist lens(es) the architect inline-empersonated during the commit's work. Codified 2026-05-26 evening.

**Why.** The **Inline = empersonate the specialist** rule (CLAUDE.md §1) is reliant on architect honesty — there's no keeper that verifies "in this commit, the backend-engineer discipline was actually applied." A commit trailer makes the lens choice **explicit + auditable** at zero infra cost.

## The trailer

```
Lenses: <name>[, <name>...]
```

Valid lens names (mirror `.claude/agents/` executor + advisor names):
- `architect` (advisor — plan/scope decisions)
- `backend-engineer` (executor — server code, services, schemas, data layer)
- `frontend-engineer` (executor — UI, components, hooks)
- `devops-engineer` (executor — containers, CI/CD, deploys, observability)
- `compliance-reviewer` (advisor — gates, sync verification)
- `security` (advisor — threat-model, auth, validation)
- `engineer-default` (executor — catch-all, when slice is methodology-internal)
- `tech-lead` (the conversational session itself — git/merge/deploy ownership; default lens)

A commit may declare multiple lenses (typical for cross-domain inline work).

## When to use

- **Inline-deving** (no dispatch): declare the lens(es) you empersonated.
- **Multi-domain commits**: list all lenses applied — `Lenses: backend-engineer, devops-engineer`.
- **Pure methodology / docs**: `Lenses: tech-lead` (default; can also omit).
- **Dispatched work**: the dispatched agent's own lens IS the lens — usually the same as the agent type. Tech-lead's integration commit can declare `Lenses: tech-lead`.

## Why a trailer, not a keeper

A keeper that **requires** the trailer would be coercive — a commit without it would fail. That mismatches the lens discipline (some commits genuinely don't need a lens beyond tech-lead; some are infra-only).

The trailer is **observability**, not enforcement:
- Allows post-hoc audit: `git log --grep "Lenses:"` shows which lenses are most-used; which are NEVER used (potential gap).
- Makes inline-empersonation a **conscious choice** at commit-time, not a vague intention.
- Composes with `Co-Authored-By:` — both are trailers, both serve attribution.

## Lifecycle (deferred — to be observed first)

Stage 1 (today): trailer convention, no keeper.
Stage 2 (after N≥50 commits observed): if architect frequently skips the trailer, evaluate whether a soft keeper (warning-only) makes sense.
Stage 3 (after Stage 2 data): consider a keeper for **specific** commit types (`feat:` / `fix:` / `refactor:`) where lens-applied matters most.

## Composes with

- [`parallelization-first-orchestration`](../architect/parallelization-first-orchestration.md) — the **inline = empersonate** rule; this trailer is its observability sibling.
- [`scoped-auto-improvement`](scoped-auto-improvement.md) — surfaced gaps could include "no lens trailer on a backend-shape commit" as a pattern.
- [`accept-with-rationale`](accept-with-rationale.md) — same family (lightweight discipline + audit trail; not a hard gate).

## Worked examples

```
feat(cache): add pgvector PostgresCacheBackend implementation

Phase 3.1 of cache-backend-portability roadmap. ...

Lenses: backend-engineer, architect

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

```
fix(deploy): correct VPS healthcheck port for n8n container

The container exposed 5678 but compose wired 8080 → daemon never green.

Lenses: devops-engineer

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

## Rationale (the honest version)

This trailer is **deliberate lightweight discipline**. Three reasons:

1. **Audit trail without enforcement** — the inline-empersonation rule risks being silently violated; a trailer surfaces the choice without coercing it.
2. **Methodology self-test** — if `git log --grep "Lenses: devops-engineer" | wc -l` is zero over a month, devops slices are being missed.
3. **Composes cleanly with future automation** — Stage 2/3 keepers can read trailers without rewriting commit-msg infrastructure.

The trailer is **OPTIONAL today**. The pattern's value compounds as the commit history accumulates — the cheap discipline pays back at retrospective time.
