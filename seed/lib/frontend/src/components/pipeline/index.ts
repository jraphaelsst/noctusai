/**
 * Pipeline — the data half of the kanban organ: DB-driven, user-editable stages.
 *
 * `KanbanBoard` (sibling) renders columns you hand it. `PipelineBoard` fetches
 * them, moves cards, and lets the user add / rename / recolour / reorder /
 * delete the stages themselves.
 *
 * Usage:
 *   import { PipelineBoard, createPipelineHooks } from "@noctusai/lib/components";
 */
export { PipelineBoard } from './PipelineBoard';
export type { PipelineBoardProps } from './PipelineBoard';

export { PipelineStagesManager } from './PipelineStagesManager';
export type { PipelineStagesManagerProps } from './PipelineStagesManager';

export { StageHeaderMenu } from './StageHeaderMenu';
export type { StageHeaderMenuProps } from './StageHeaderMenu';

export { DeleteStageDialog } from './DeleteStageDialog';
export type { DeleteStageDialogProps } from './DeleteStageDialog';

export { MotivoMoveDialog } from './MotivoMoveDialog';
export type { MotivoMoveDialogProps } from './MotivoMoveDialog';

export { AddStageColumn } from './AddStageColumn';
export type { AddStageColumnProps } from './AddStageColumn';

export { mergeVisibleStageOrder } from './stageOrder';
export type { OrderableStage } from './stageOrder';

export { createPipelineHooks } from './createPipelineHooks';
export type {
  PipelineHooks,
  MoveVariables,
  StageCreateInput,
  StageUpdateInput,
} from './createPipelineHooks';

export {
  STAGE_COLOR_CLASSES,
  STAGE_COLOR_OPTIONS,
  STAGE_ROLE_LABELS,
  stageColorClasses,
} from './stageTokens';
export type { StageColorClasses } from './stageTokens';

export type {
  PipelineApi,
  PipelineColumn,
  PipelineDescriptor,
  PipelineStage,
  StageColor,
  StageRole,
  DefaultStageRole,
  StageRoleLabels,
  MoveDecision,
  MoveIntentContext,
} from './types';
