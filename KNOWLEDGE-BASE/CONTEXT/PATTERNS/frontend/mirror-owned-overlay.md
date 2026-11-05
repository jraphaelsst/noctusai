# Mirror + owned overlay — every data UI ships with data management

> **Rule.** A screen that shows data from an external system (Vista, a CRM, a bank feed) next to data WE author is a **mirror plus an owned overlay**. Every field on it declares its **source** (mirror or owned) and its **CRUD verbs**. Mirror fields are **read-only, with provenance and freshness**. Owned fields get **full CRUD**. A **sync never overwrites owned data**. Where we hold a value that differs from the mirror, **both are shown**. A UI is not done until this table is written down and true.
>
> Extends `product-internal-wiring.md` §2a (page-scoped CRUD): that rule says the page that lists an entity manages it; this one says *which fields of a mirrored entity are manageable, and how the screen tells the operator*.

## 1 · Why (owner directive, 2026-11-03)

social-wiring's imóvel page is "a mirror of Vista's data, with our own data added over time — not replacing theirs, adding to it". Before this rule the page rendered both kinds with the same visual weight, offered a pencil on every Vista section that only toasted "edição não disponível" (a button that edits nothing), had no place for our own notes, and could not show that our area differed from Vista's. Future UIs must be built with the data management designed in, not retrofitted.

## 2 · The six rules

### (a) Every data UI declares each field's source and CRUD verbs
Before building, write the **field table** (it goes in the PR/report and, for non-trivial surfaces, in the component's header comment):

| Field | Source | C | R | U | D | Endpoint / owner |
|---|---|---|---|---|---|---|
| `valor_venda` | mirror (Vista) | no | yes | no | no | `GET /api/imoveis/{codigo}` |
| `area_terreno_m2` | owned (overrides mirror) | yes | yes | yes (PATCH null clears) | yes (clear) | `PATCH /{codigo}/dados` |
| notas | owned collection | yes | yes | yes | yes (confirm) | `/{codigo}/notas` |

A field with no row is an unaudited field. `noc-wiring-audit` runs this table.

### (b) Mirror fields are read-only, with provenance and freshness
- Mark the section/field with the seed organ `SourceBadge` (`@noctusai/lib/components`): `Vista · há 2 h`, tooltip says why it is read-only. **Never a dead edit button** — a control that opens nothing is a silent error; the badge says *why* there is no editor.
- Freshness comes from the mirror's own sync timestamp (`sincronizado_em`), provided once per page (social-wiring: `VistaSyncProvider`) so every section shows the same time.
- No endpoint of ours writes a mirror column. The write is refused at the service, not hidden in the UI.

### (c) Owned fields get full CRUD
- **Create / edit / clear**: persisted to the owned table through the **existing service** for that data (`imovel_dados` via `dados_service.atualizar`, notas via `notas_service`). Extend a service only where a verb is missing; never a parallel store.
- **Clear** is a real verb: `PATCH` with `null` (absence = leave alone, `null` = clear — `model_fields_set`).
- **Collections** (documents, notes, links) get add / edit / remove, and **remove asks first** (`useConfirm`, `tone: 'danger'`).
- Every write uses `useCacheWriteMutation` (`mutation-cache-writes.md`): optimistic draw or commit of the server row, never invalidate-only.
- States: loading skeleton off `isPending && !data` (`lying-loading-state.md`), error before empty (`silent-refusal.md`), empty, success; a refusal is drawn under the form it came from; a typed draft says it is unsaved (`UnsavedChangesNotice`).
- Backend: org-scoped, auth `== 401` test, actor stamped (`created_by` / `updated_by` / `confirmado_por`), 404 (not 200) when deleting what does not exist.

### (d) A sync never overwrites owned data
- Owned data lives in **its own table or columns** (`imovel_dados`, `imovel_notas`, …), keyed to the registry — never inside the mirror table the sync upserts.
- The sync's upsert list names the mirror columns explicitly; an owned column added to the mirror table is a defect (the sync would eventually clobber it).
- A human's value beats a machine reading (provenance quintet / `confirmado_*`); a disagreement becomes a conflict a human decides, not an overwrite.

### (e) Where ours differs from the mirror, show both
`<MirrorOverrideValue mirror="280 m²" owned="300 m²" />` renders `Vista: 280 m² · Nosso: 300 m²` only when both exist and differ; one value when they agree or only one exists. The component **never decides precedence** — the backend's existing precedence is authoritative and the UI renders what it resolved. Do not invent a new precedence in a component.

### (f) External-mirror divergence review: a human decides, the sync never overwrites
When the mirror and OUR value for the same fact disagree (e.g. a Julia conversation set the area, the next Vista sync says otherwise), the system **flags** it and a **person resolves** it — never a silent last-writer-wins.
- Detection is backend-side on the existing conflict machinery (`imovel_campo_conflitos`); the sync writes a flag, not the column.
- UI: a block "Divergências com o Vista" rendered **only while ≥1 is pending**, a count badge on the diverging field rows, each item showing both values with dates, **the origin of our value** (e.g. a link to the Julia conversation + a sanitized excerpt, never raw PII), and three actions — *Usar Vista* / *Manter o nosso* / *Corrigir* (manual value). History collapsed. Read open, buttons org-admin (server enforces).
- Resolution goes through `useCacheWriteMutation` (item leaves "pending" on the click); a refusal is drawn on the item.
- Transitional by design: the whole review lives in one component + one hook file + one mount (social-wiring: `ImovelDivergenciasVista`, `useImovelDivergencias`) so it can be deleted without touching the page. Use the existing binary `ConflitosPendentesCard` when the decision is only accept/reject of a machine reading; this three-way review is for mirror-vs-owned.

## 3 · Checklist for a new data UI

1. List every field/collection with its **source** and **C/R/U/D** (rule a). Anything external → mirror; anything we author → owned.
2. Mirror sections: `SourceBadge` + shared freshness; **no edit affordance**; confirm the backend refuses writes to those columns.
3. Owned fields/collections: an endpoint per missing verb (extend the existing service), strict-auth test, org scoping, actor stamp.
4. Overlap (we hold a value for a mirrored fact): `MirrorOverrideValue`, using the backend's resolved precedence.
5. Every write through `useCacheWriteMutation`; loading / error / empty / success; refusal visible; draft flagged unsaved; collection removes confirm.
6. Prove the sync leaves owned data alone (a test that runs the owned write, then the sync's upsert, and compares).
7. If the mirror can disagree with an owned value, add the divergence review (rule f) instead of letting either side win silently.
8. Register new organs (`.organ.yaml`) and reuse the lib ones before writing local copies (`products-consume-canonical-organs.md`).

## 4 · Reference implementation

social-wiring imóvel detail (`products/social-wiring/frontend/src/pages/ImovelDetalhes.tsx`): mirror sections via `SectionCard` (Vista badge + sync time), owned cards (cartório, endereço manual, avaliação with `Vista: X · Nosso: Y` areas, referências, documentos, notas internas). Notes: migration 315, `modules/imovel_hub/notas_service.py`, `ImovelNotasCard`. Organ: `SourceProvenance` (`seed/lib/frontend/src/components/provenance/`).

## 5 · Provenance
Born 2026-11-03 from the owner's request for the imóvel UI. Composes with `product-internal-wiring.md`, `mutation-cache-writes.md`, `lying-loading-state.md`, `silent-refusal.md`, `products-consume-canonical-organs.md`.
