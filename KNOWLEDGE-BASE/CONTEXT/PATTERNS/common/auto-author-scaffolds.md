# Auto-author scaffolds — starting points, not finished artifacts

**What it is.** Three scaffold generators for the codification pipeline:
- `scaffold_memory_entry(name, description, target?)` → draft `feedback_<name>.md`.
- `scaffold_kb_pattern_draft(name, description)` → draft KB pattern doc.
- `scaffold_keeper_function(name, description)` → draft `check_<name>` skeleton.

Born v4.0-beta follow-up (F12). The original diagnostic correctly flagged judgment-heavy auto-authoring as risky. This module deliberately ships only the **mechanical scaffolding** part (template + placeholders + vector-matched references) and explicitly does NOT write content the architect should write.

## What scaffolding catches

The "blank-page" friction:
- "What sections does a memory entry have? Let me check an existing one."
- "What's the standard KB pattern doc structure?"
- "What's the issue-dict shape for a keeper?"

These are STRUCTURAL questions with mechanical answers. Filling templates with `<TODO>` placeholders saves the lookup. Each scaffold:
1. Emits the structural skeleton.
2. Marks every judgment-required field with `<TODO>`.
3. Vector-matches against existing artifacts of the same kind and lists "similar existing" references — the human reads them BEFORE filling the TODOs.

## What scaffolding does NOT catch

Content quality. The scaffolds are starting points. The architect/agent does the judgment:
- WHY this rule (the WHY clause).
- WHEN it fires (the predicate).
- HOW to apply (the diagnostic).
- WHICH related patterns it composes with.

## API

```python
auto_author_scaffolds.memory_entry(name, description, target=None) -> dict
# Returns: {ok, filename_suggestion, content, similar_existing}

auto_author_scaffolds.kb_pattern(name, description) -> dict
# Returns: {ok, filename_suggestion, content, similar_existing}

auto_author_scaffolds.keeper(name, description) -> dict
# Returns: {ok, code, kb_doc_pointer_suggestion, next_steps}
```

## When to use

- Architect/agent starts a codification (s2→s3 promotion, new memory entry).
- The structural overhead is real but boilerplate.
- Wanting a quick "similar existing" reference list.

## When NOT to use

- The scaffold's similar-existing list shows the artifact already exists. Extend; don't create.
- The judgment work isn't ready (rule isn't crisp; predicate not deterministic). Author from scratch with the right pacing.

## Composes with

- [`methodology-codification-pipeline`](methodology-codification-pipeline.md) — the pipeline this scaffolds artifacts for.
- `/codify` (the decision layer over the codification debt).
- `kb_embeddings.search` (the similar-existing source).
- `scaffold_keeper`, `scaffold_memory` (existing scaffolders this is the AI-augmented sibling of).

## Anti-patterns

- **DON'T** commit the raw scaffold output. Always replace every `<TODO>` first.
- **DON'T** trust the "similar existing" list as exhaustive. It's vector-rank; verify with grep.
- **DON'T** use the keeper scaffold without writing the test alongside.
