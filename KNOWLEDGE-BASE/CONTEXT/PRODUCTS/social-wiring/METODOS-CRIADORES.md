# Métodos de criadores — one template for every reference creator's methodology

> Status: v1, 2026-11-19. Home: `products/social-wiring/backend/app/modules/media_creation/metodos_criadores/<slug>.json`,
> validated by `metodo_criador.py` (schema + loader) and `tests/modules/media_creation/test_metodo_criador.py`.

## What it is

A **method** is the FORM of a reference creator's content (Elias Maman, Alba Valéria, later Fernando Segredo…):
the emotional curve, the moldes as ordered steps with timings and word ranges, why each works, what may and may not
be copied, and a pre-recording checklist. One JSON file per creator, all in one schema, so any writer (agent or
product stage) consumes any method the same way, and a new creator is a new file — never a new agent or skill.

## Three layers, three homes

| Layer | Holds | Home |
|---|---|---|
| **Method** (reference creator) | curve, moldes, rules, checklist — form only, never their words or transcripts | `metodos_criadores/<slug>.json` (this repo) |
| **Client** (the creator we write for) | voice, audience, ethics, approved scripts, examples of each method written for them | the client's private folder (client data, outside git) |
| **Writer** | applies a chosen method to a client | one roteirista agent per client (`roteirista-<cliente>`), which receives `método: <slug>[/molde-N] \| auto` and reads ONLY that file |

Cost rule: a writer reads only the chosen method, never all of them. Agent-per-client stays until the 3rd client
(DRY recurrence rule); then the client-agnostic rules (CTA chosen by the post's goal, humanize, never invent a
source, copy form not words) lift into one shared base.

## Schema (v1) — enforced, not described

- Every `moldes[].etapas[].bloco` MUST be a canonical block type from `estruturas_tipos_bloco.TIPO_NOMES`. This is
  what makes a method importable into the CoreStudio Estruturas library later (`perfil` = `criador.handle`).
- Moldes numbered `1..N` in order, unique slugs, `0 < min <= max` for `duracao_s` and `palavras`.
- `extra="forbid"`: an unknown field (e.g. pasted transcripts) is refused.
- The file name must equal `slug`. `listar()` raises on an invalid file; it never skips one.

## Adding a creator

1. Study the profile (skill `noc-ig-analysis`, profile mode) — transcripts stay in `_private-studies/`.
2. Write `<slug>.json` in the schema; keep only form. Client examples go to the client's folder.
3. Run the test; it must pass with the new file.
4. The "Metodologias de criadores" artifact renders every file with the same layout (the Alba Valéria study layout).

## Later: into the product

Each molde becomes an Estruturas row (blocks = its steps, `perfil` = the creator handle), and the headline/roteiro
pipeline picks it by `perfil`. The JSON is the source until that import lands; after it, the product library is.
