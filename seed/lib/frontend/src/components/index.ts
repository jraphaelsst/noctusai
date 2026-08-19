export { ErrorBoundary, withErrorBoundary } from './ErrorBoundary';
export { SSOCallback } from './SSOCallback';
export type { SSOCallbackProps } from './SSOCallback';
export { createAuthProvider } from './AuthProvider';
export { FakeModeBadge } from './FakeModeBadge';
export type { FakeModeBadgeProps, FakeModeBadgeVariant } from './FakeModeBadge';
export { ResourceManager } from './ResourceManager';
export type {
  ResourceManagerProps,
  ResourceColumn,
  ResourceField,
  ResourceFieldType,
} from './ResourceManager';
export { StatusPaginaPanel, STATUS_PAGINAS_QUERY_KEY } from './StatusPaginaPanel';
export type {
  StatusPaginaPanelProps,
  StatusPaginaApi,
  StatusPaginaRow,
  StatusPaginaStatus,
} from './StatusPaginaPanel';

// Detail — THE one record-detail modal. Layout lives here; the field list
// is a descriptor the consumer builds once per entity, so a table row, a
// kanban card and a search result all open the SAME modal and a new field
// is one edit rather than N.
// `DetailSections` is the field grid ALONE — for a surface that must show a
// record's fields without being a dialog (social-wiring's lead card renders it
// inline). Same renderer, so the two cannot drift.
export { DetailSections, EntityDetailDialog } from './detail';
export type {
  DetailAction,
  DetailField,
  DetailSection,
  EntityDetailBadge,
  EntityDetailDialogProps,
} from './detail';

export { KanbanBoard, KanbanColumn, KanbanCard } from './kanban';
export type {
  KanbanBoardProps,
  KanbanColumnProps,
  KanbanCardProps,
  KanbanStage,
  KanbanColumnData,
  KanbanCardRenderState,
  KanbanOnMove,
} from './kanban';

// Pipeline — the data half of the kanban organ (DB-driven, editable stages).
// `KanbanBoard` renders columns you hand it; `PipelineBoard` fetches them,
// moves cards, and ships the stage editor.
export {
  PipelineBoard,
  PipelineStagesManager,
  createPipelineHooks,
  STAGE_COLOR_CLASSES,
  STAGE_COLOR_OPTIONS,
  STAGE_ROLE_LABELS,
  stageColorClasses,
} from './pipeline';
export type {
  PipelineBoardProps,
  PipelineStagesManagerProps,
  PipelineHooks,
  PipelineApi,
  PipelineColumn,
  PipelineDescriptor,
  PipelineStage,
  StageColor,
  StageColorClasses,
  StageRole,
  MoveVariables,
  StageCreateInput,
  StageUpdateInput,
} from './pipeline';
