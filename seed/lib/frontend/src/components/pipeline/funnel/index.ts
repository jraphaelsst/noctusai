/**
 * Funnel organ — ONE board + card for every product, declared per product by a `FunnelSchema`.
 * `KB § PATTERNS/frontend/funnel-organ.md`
 */
export { defineFunnel } from './defineFunnel';
export type { DefinedFunnel } from './defineFunnel';

export { createFunnelHooks, showsStatus, mergeChanges } from './createFunnelHooks';
export type { FunnelHooks, FunnelDescriptor, LoseVariables, ActionVariables, ActionResult } from './createFunnelHooks';

export { FunnelBoard } from './FunnelBoard';
export type { FunnelBoardProps } from './FunnelBoard';
export { FunnelCardFace } from './FunnelCardFace';
export type { FunnelCardFaceProps } from './FunnelCardFace';
export { FunnelCardDialog } from './FunnelCardDialog';
export type { FunnelCardDialogProps } from './FunnelCardDialog';
export { LostReasonDialog } from './LostReasonDialog';
export type { LostReasonDialogProps } from './LostReasonDialog';
export { FunnelActionDialog } from './FunnelActionDialog';
export type { FunnelActionDialogProps } from './FunnelActionDialog';
export { useFunnelActionFlow } from './useFunnelActionFlow';

export { FieldsGridSection, displayField } from './sections/FieldsGridSection';
export type { FieldsGridSectionProps } from './sections/FieldsGridSection';
export { LinkedEntitiesSection } from './sections/LinkedEntitiesSection';
export type { LinkedEntitiesSectionProps } from './sections/LinkedEntitiesSection';

export { formatFunnelValue, initialsOf } from './format';
export { parseFunnelError } from './funnelError';

export type {
  FunnelStatus,
  FunnelBadge,
  FunnelCard,
  FunnelLostReason,
  FunnelGate,
  FunnelMeta,
  FunnelMetaAction,
  FunnelPendencia,
  FunnelRefusal,
  FunnelFaceSlots,
  FunnelFaceAction,
  FunnelFaceIconAction,
  FunnelFieldDef,
  FunnelLinkedColumn,
  FunnelSection,
  FunnelSectionRenderCtx,
  FunnelTab,
  FunnelActionDef,
  FunnelActionInput,
  FunnelSchema,
  FunnelRenderers,
} from './types';
