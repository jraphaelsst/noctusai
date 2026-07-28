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
