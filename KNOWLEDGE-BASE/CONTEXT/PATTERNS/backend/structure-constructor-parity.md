# Structure ↔ constructor parity — a field reaches every function that builds the entity

> **Rule.** When an entity's STRUCTURE changes (a field on its record, a column on its row), every function that CONSTRUCTS it changes in the SAME commit: the store's create signature, the insert payload, the row → record mapping, the create request and response models, the route that forwards the body, and every agent-facing payload list (MCP tools). A surface that legitimately does not carry the field says so, with the reason, in the entity's `structure_parity.py` manifest. Keeper `check_structure_constructor_parity` holds it (pre-commit; WARN-only shadow since 2026-11-08, promoted to blocking after the ≥7-day shadow record, per `KB § PATTERNS/common/gate-methodology-sync.md`; decision D24).

Born 2026-11-08. Owner, on adding `kind`/`fonte` to agents: *"put a gate here, whenever we change the agent structure, we must update the function to match it. tests will probably pass, but it will break if we change the structure and not the function that creates them … doc this as knowledge so we fan this out in the future as fundamentals."*

---

## 1 · Why tests don't catch it

Each surface DEFAULTS the field. The record has `kind: str = "runtime"`, the create function has `kind="runtime"`, the request model has `default="runtime"`. A unit test of any one surface passes. The break is in the CHAIN: a value set at the top never reaches the row, because one link in the middle never accepts it. It stays invisible until someone tries to create a non-default entity through the real path, often in production.

Measured on the first run: against `origin/dev`'s creation code, the keeper flagged **6 surfaces**. It also found a gap that was already there: `kind` had never been creatable through `POST /plataforma/agents`, so a platform definition could only ever be `runtime`.

## 2 · The mechanism (construction leg)

A manifest beside the entity, read by AST and never imported:

```python
# products/<slug>/backend/app/stores/structure_parity.py
STRUCTURE_PARITY = {
    "agent": {
        "record": "products/agents/backend/app/stores/studio_definitions.py::StudioAgentRecord",
        "surfaces": [
            {"name": "Supabase insert payload",
             "target": ".../studio_definitions.py::SupabaseStudioDefinitionStore.create_studio_agent",
             "kind": "dict_keys:payload",
             "exempt": {"id": "set by the database", ...}},
            ...
        ],
    },
}
```

Surface kinds: `fields` (class fields; the record uses it too) · `params` (function parameters) · `call_kwargs:<Fn>` (keywords passed to `<Fn>(...)` inside the target) · `dict_keys:<var>` (keys of the dict literal assigned to `<var>`) · `tuple` (a module-level string tuple; `*OTHER` expands).

The keeper fails on four things:
- a record field not carried on a surface and not exempted;
- an exemption for a field the record no longer has (a stale reason hides the next drift);
- an exemption without a reason;
- a target that no longer resolves (renamed function).

## 3 · How to apply

- **Adding a field:** carry it on every surface, or exempt it with the real reason ("set by the database", "derived from X", "admin-only toggle"). "Not needed yet" is not a reason. It is the gap this rule exists to close.
- **Adding a constructor** (a new route, tool or importer): add it to the manifest as a surface in the same commit. The keeper cannot discover constructors it was not told about. That is the one hand-maintained part, and it lives in one file beside the record.
- **Immutable fields** (`kind`, `fonte`) are creation-only. They belong on the create surfaces and are exempted on update surfaces.

## 4 · Fan-out (named next entities)

Each one is a manifest entry, not a new keeper:

| Entity | Record | Constructor surfaces to declare |
|---|---|---|
| agent version / draft | `VersionRecord` | `create_draft`, `_DRAFT_FIELDS`, draft PATCH request, `rascunho_padrao` validator |
| eval case | `EvalCaseCreateRequest` | the store insert, `noctus.agents.content` `_EvalCases` field tuples (both suites) |
| library skill | skill version record | `/api/skills-biblioteca` create, MCP `skill` kind fields |
| any product entity with a create route + an MCP/content tool | its record | same chain as agents |

Next leg (not in v1): the TypeScript side. The "Novo agente" form and its zod schema are constructor surfaces too. A `ts` surface kind (via ts-morph, AST-first) closes it. Destination: the agent-creator build, which wires that form to "gerar com IA".

## Composes with

`KB § PATTERNS/devops/product-lockfile-and-slug-drift.md` (the same "hand-maintained list drifts" family, applied to code shapes) · `KB § PATTERNS/common/gate-methodology-sync.md` (build triad) · `KB § PATTERNS/common/ast.md` · `products/agents/projects/agent-packages/CONTRACT.md` §M (where it was born).
