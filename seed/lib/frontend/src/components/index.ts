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

// API keys — org-scoped, operator-settable managed credentials (lifted from
// social-wiring's Settings "Chaves de API" tab as a pure addition).
export { createApiKeysHooks, ApiKeysPanel } from './api-keys';
export type {
  ApiKeysHooks,
  CreateApiKeysHooksOptions,
  ApiKeyOption,
  ApiKeySource,
  ApiKeyStatus,
  ApiKeysStatus,
  ApiKeyTestResult,
  ApiKeySave,
  ApiKeysPanelProps,
} from './api-keys';

// WhatsApp connections — multi-line WAHA connection management (lifted from
// social-wiring's Conexoes/Conexao pages as a pure addition).
export {
  createWhatsAppConnectionsHooks,
  WhatsAppConnectionsPage,
  CreateConnectionDialog,
  ConnectionDetailDialog as WhatsAppConnectionDetailDialog,
} from './whatsapp-connections';
export type {
  WhatsAppConnectionsHooks,
  CreateWhatsAppConnectionsHooksOptions,
  WhatsAppConnectionLine,
  WhatsAppConnectionStatus,
  WhatsAppConnectionQr,
  WhatsAppConnectionRecoverResult,
  WhatsAppConnectionWebhookResult,
  CreateWhatsAppConnectionBody,
  UpdateWhatsAppConnectionBody,
  ConfigureWhatsAppConnectionWebhookBody,
  WhatsAppConnectionsPageProps,
} from './whatsapp-connections';

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
  MotivoMoveDialog,
  createPipelineHooks,
  STAGE_COLOR_CLASSES,
  STAGE_COLOR_OPTIONS,
  STAGE_ROLE_LABELS,
  stageColorClasses,
} from './pipeline';
export type {
  PipelineBoardProps,
  PipelineStagesManagerProps,
  MotivoMoveDialogProps,
  PipelineHooks,
  PipelineApi,
  PipelineColumn,
  PipelineDescriptor,
  PipelineStage,
  StageColor,
  StageColorClasses,
  StageRole,
  MoveVariables,
  MoveDecision,
  MoveIntentContext,
  StageCreateInput,
  StageUpdateInput,
} from './pipeline';

// Card hub — the entity-agnostic card organ: 3-pane detail dialog with a
// subpage registry (rail + subpage + activity), board face, kind-registry
// timeline, Geral subpage with named slots, and `createCardHubHooks` (the
// data layer, query keys derived from `rootKey`). Moved from social-wiring's
// lead card — `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`.
export * from './card-hub';

// Markdown — canonical GFM renderer organ (tables/task-lists/strikethrough,
// slugged headings, sanitized by construction — no raw HTML execution).
// Consuming pages own the "where do docs live" question via the
// `resolveImage`/`onNavigate` seams; the organ never touches a bundler API.
export { MarkdownRenderer } from './markdown';
export type { MarkdownRendererProps } from './markdown';
