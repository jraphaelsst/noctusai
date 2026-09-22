# Wave A design — seed CardHub extraction + SW swap (architect, 2026-09-22)

Companion to `cardhub-igig-crm-2026-09.md`. Verdict **[F]ormalize** — redeems D13/S3 of `products/social-wiring/projects/lead-card-hub-p2-PROJECT.md:21` ("lifting later must be a MOVE, not a rewrite").

## Tech-lead decisions
- **D-A1** Lift over the PostgREST `db` seam (same seam as `noctusai_lib.domain.pipeline`), NOT RecordStore. Fake = `noctusai_lib.testing.MockSupabaseClient`. igig will use its Supabase client for pipeline + card-hub modules; RecordStore gaps tagged `NOC-REMEDIATE[card-hub-recordstore]`.
- **D-A2** SW desktop rendering stays identical; phone widths (<640px) may gain the full-screen-sheet layout (mobile-first mandate R0) — additive only.
- **D-A3** SW API contract byte-identical (see §5).

## 1. Generic (→ seed) vs SW-specific (stays)
**BE → `seed/lib/backend/noctusai_lib/domain/card_hub/`**: `services.py` (notas descricao/comentario + soft-delete + typed 409 on 2nd descricao; tags catalogue+links SW `services.py:271-380`; membros `:382-429` with pluggable member source; checklists+itens `:431-641`; `ensure_*`), `timeline.py` (cursor codec, `get_timeline`, gatherer registry — SW `timeline_service.py:39-448`; seed ships `nota`,`documento`,`checklist` gatherers), `badges.py` (`compute_badges`/`get_card_resumo` `timeline_service.py:466-567` + extension hook), `documentos.py` (from `documentos_service.py`: LGPD access log, tipos, signed URL, retention sweep — retention registration an explicit call, not import side effect `__init__.py:78`), `checklist_extras.py` (083), `lembretes.py`; lift SW `app/services/table_reads` helpers (`paged_rows`,`in_batched_rows`,`resolve_actors`) next to seed `integrations/persistence/paging.py`.
**BE stays SW** (plugged via registry): compradores/vendedores/partes, negociação(+estruturada), financiamento, contratos + gerador + assinatura, roteiros/visitas/imóveis, atendimento_agendamentos(061), documento_checklist(067), identidade/conflitos/qualificação/certidões, timeline gatherers `touch`,`movimento`,`visita`,`sistema`.
**FE → `seed/lib/frontend/src/components/card-hub/`**: 3-pane dialog shell (chrome of `ClienteCardDialog.tsx:489-1046`: rail + middle + activity pane + error/loading/not-found), `CardSidebarNav` (registry-driven), `Timeline` (kind-renderer registry, keeps unknown-kind fallback), `ClienteCardFace`→`CardHubFace`, Etiquetas/Membros/Checklist popovers, `DescricaoSection`, `ChecklistsSection`/`ChecklistBlock`, `ComentarioComposer` (`:1404-1836`), `AnexosSection`, `ChecklistExtrasSection`, `ChecklistItemRow`, `CollapsibleSection`, `TooltipIconButton`, `TokenCheckbox`; generic slice of `useCardHub.ts` (resumo, timeline, notas, tags, membros, checklists, documentos, checklist-extras).
**FE stays SW**: `ContatoResumo`, `PessoaDocumentosSection`, `PapelSelect`/`PAPEL_LABEL`, `useRecordSections`, vendedor block, all Negociação/Financiamento/Contratos/Roteiros/Matrícula/Gerador panels + their hooks.
**Leaks to keep local**: `ClienteCardDialog.tsx:73-78` imports `@/pages/leads/leadDetailSections`; `CriarRoteiroDialog.tsx:55`, `ImovelCodigoPicker.tsx:34` import `useCardHub` hooks.

## 2. Seams
```python
@dataclass(frozen=True)
class CardHubTables:  # every name overridable ⇒ SW keeps its tables, zero DDL
    notas; tags; tag_links; membros; lembretes; checklists; checklist_itens
    checklist_extras; documentos; documento_tipos; documento_acessos   # defaults "{prefix}_<name>"
@dataclass(frozen=True)
class CardHubConfig:
    entity_kind: str; entity_table: str; entity_fk: str; id_param: str  # SW: "cliente","clientes","cliente_id"
    table_prefix: str; tables: CardHubTables
    member_source: MemberSource  # SW: table="lead_corretores", fk="lead_corretor_id", label="nome", cor="cor"
    ensure_entity: Callable      # SW: clientes_svc.get_cliente
    bucket: str                  # SW "social-wiring-documentos" (existing object paths)
    timeline_gatherers: Mapping[str, Gatherer] = SEED_GATHERERS
    badge_extensions: Sequence[Callable] = ()
```
Router factory `card_hub_routers(cfg, *, auth_dependency, resolve_context, get_db, get_storage, prefix) -> (collection_router, entity_router)` — takes product `get_db`/`get_storage` deps (keeps SW `get_card_hub_client` + test overrides `tests/modules/card_hub/conftest.py:81`); two routers so literal routes (`/tags`, `/documentos/tipos`) mount before `/{id}` (route-order fix `card_hub/__init__.py:14-19`); `CardHubContext(db, org_id, user_id)` like `PipelineContext` (`pipeline/router.py:64`). **Never** call `get_admin_client().schema(...)` inside the factory (schema-poisoning fix `62f82ba47`).
Migration template `domain/card_hub/sql.py::card_hub_migration(cfg, schema)` emits 056+057+083 DDL via `sql_templates` (search_path, service_role_bypass, rls_subquery_policy), incl. partial-unique descricao index + documento RLS. SW never runs it; parity test asserts it matches SW columns.
FE: `createCardHubHooks({rootKey, basePath, entityLabel}, api)` mirroring `createPipelineHooks` (`pipeline/createPipelineHooks.ts:56`). SW passes `rootKey: ["sw","cardHub"]` (query keys byte-identical, `useCardHub.ts:72-116`). `useCardHub.ts` keeps SW-only hooks and re-exports generated ones under the same names.
Subpage registry:
```ts
interface CardSubpage<K extends string> { key: K; label: string; icon: LucideIcon;
  render: (ctx: CardHubRenderCtx) => ReactNode; isEmpty?: boolean; toolbar?: ReactNode }
<CardHubDialog subpages defaultSubpage onSubpageChange testId="cliente-card-dialog"
  headerActions activity={{timeline, composer}} geral={{slots:{afterTags, afterDescricao, beforeAnexos}}} />
```
Seed ships `GeralSubpage` (tags, descrição, anexos, checklists + named slots). `ClienteCardDialog` becomes a thin SW adapter with the SAME props (`:140-463`) → `ClienteDetailModal` and the 2325-line `ClienteCardDialog.test.tsx` stay unchanged = zero-behaviour proof. Mobile: dialog renders as full-screen sheet <640px, rail becomes horizontal scroll tabs.

## 3. Pipeline editable columns (seed)
Exists: stage CRUD per board, delete requires target + refuses `papel` stages (`stages.py:316`), deactivate guard (`:267`), `POST /reordenar` (`:350`), optimistic `useReorderStages`, `PipelineStagesManager` up/down + papel badge (`:172-204`).
Missing: (1) `editableHeaders` prop on `PipelineBoard` (`renderColumnHeader` `:192`) → `StageHeaderMenu` inline rename/recolor/delete via extracted `DeleteStageDialog`, trailing "+ coluna" (`KanbanBoard.renderTrailingColumn`); (2) column drag-reorder: horizontal SortableContext of columns INSIDE the single existing `DndContext` (`KanbanBoard.tsx:201`), discriminate by `data.type`; `computeMove.ts` ignores column drags; opt-in `onColumnReorder(ids)` → `useReorderStages`; (3) roles closed set of 2 in `stages.py STAGE_ROLES`, FE `StageRole` (`types.ts:38`), SW CHECK (`034:71`) → `PipelineConfig.stage_roles` (default = current two) + FE descriptor `roleLabels`; (4) `canEditStages` FE prop + optional `require_stage_admin` BE dependency. Mobile: TouchSensor/press-delay so drag works on phones without hijacking scroll; board scrolls horizontally inside its container only (no page overflow).

## 4. Slices
| # | Slice | Depends | Collision |
|---|---|---|---|
| A | seed BE `domain/card_hub/*` + table_reads lift + SQL template + seed tests (ports of SW `test_notas_tags_membros`, `test_checklists`, `test_timeline`, `test_documentos`, `test_checklist_extras`, run vs neutral `lead` cfg and SW-shaped cfg + template parity) | — | C1 |
| B | seed UI primitives (Popover, Checkbox, Switch, Avatar, ScrollArea, Progress, Textarea, Select) + radix deps | — | C3 (`check_framework_deps fix=True` rewrites every products/*/frontend/package.json — run alone) |
| C | seed FE `components/card-hub/*` + `createCardHubHooks` + organ.yaml | B | C1 |
| D | seed pipeline editable columns FE+BE | — | C1 |
| E | SW BE swap onto factory (services/timeline become shims + SW gatherers; `stage_gate.py:52` import unchanged) | A | C1 vs F |
| F | SW FE swap: `ClienteCardDialog` → adapter; delete lifted components; `useCardHub` on `createCardHubHooks` | C | C1 vs E |

## 5. Must stay byte-identical (SW)
Every path/method/status (201 create, 204 delete); query params `cursor`, `limit` 1–200, `kinds` CSV, `motivo` query; response keys (timeline `{items,total,next_cursor}` flattened payload; `CardResumo` badges/descricao); typed 409 + `NotFoundError("lead_corretores",…)`; cursor encoding; bucket + object-key layout + access-log rows; retention job id (no double registration); query-key root `["sw","cardHub"]`; DOM test ids.
Verify: route inventory diff `[(r.path, sorted(r.methods)) for r in app.routes if r.path.startswith("/api/clientes")]` before/after identical incl. order + OpenAPI diff; unchanged SW generic suites (`git diff --stat` empty on `tests/modules/card_hub` + `components/card/*.test.tsx`); gate_sweep on merged tip; `predeploy_check social-wiring`; local smoke (card from /funil, /clientes, ProcessosVenda; all rail subpages; timeline load-more; nota CRUD + 409 toast; checklist; document upload/open/delete+motivo/re-extract; etiquetas + membros) at desktop AND 390px.

## Risks
Visual drift from seed primitives replacing SW shadcn copies (keep markup/test ids); `SupabaseRecordStore.list` has no paging (`supabase_adapter.py:116-120`, 1000-row cap) — fix-on-contact candidate; `check_canonical_organ_consumption` will flag SW leftovers → declare registry entries as named-seam extensions. `feat/igig-foundation` pointer `on_going` since 2026-08-09 but dead (commit absent) — close before igig slices.
