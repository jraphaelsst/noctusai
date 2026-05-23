# `doc/` — the guide manual

Central hub for this repo's documentation: how we work, how the system is shaped,
and the knowledge that isn't obvious from the code. If something is a durable
instruction, methodology, or decision, it belongs here.

> **Scope.** `doc/` holds **developer / process documentation** (how we build).
> The **course knowledge base** (the extracted methodology itself) lives in
> [`../data/methodology/`](../data/methodology/) — that's product data, not dev
> docs. This README links to both.

## Contents

| Doc | What it is |
|---|---|
| [branching-dispatch.md](branching-dispatch.md) | Our parallel multi-agent dev workflow. Triggered by "dispatch / branch agents or a task". main is the frozen safety net; `methodology-dev` is the integration branch; workers run in parallel branches; the supervisor reconciles and lands the result. |
| [methodology-assessment.md](methodology-assessment.md) | Honest rating of the "Método Audience" methodology against validated sources, and the gaps the enrichment closed. |

## Pointers (authoritative sources elsewhere)

- [`../CLAUDE.md`](../CLAUDE.md) — agent operating rules (auto-loaded every session). The 🔒 protected-`main` rule lives here.
- [`../README.md`](../README.md) — human quickstart (install / run the pipeline).
- [`../data/methodology/ESQUEMA-BASE-DE-CONHECIMENTO.md`](../data/methodology/ESQUEMA-BASE-DE-CONHECIMENTO.md) — the agent-ready knowledge-base schema + reasoning flow.
- [`../data/methodology/REFERENCIAS.md`](../data/methodology/REFERENCIAS.md) — canonical bibliography for every methodology claim.

## Conventions

- **`.docx` are generated artifacts, not source.** The source of truth is the
  `.md` files. Regenerate docx on demand via the repo's converter
  (`app.services.docx_export.md_to_docx` / `export_methodology_docx`); they are
  gitignored, not version-controlled.
- **Branch safety:** `main` is never touched without explicit per-action consent.
  All work happens on `methodology-dev`.
