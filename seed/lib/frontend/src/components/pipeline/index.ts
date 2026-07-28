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
} from './types';
