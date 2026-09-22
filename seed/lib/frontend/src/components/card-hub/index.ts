/**
 * Card hub — the entity-agnostic "card" organ (3-pane detail dialog, board
 * face, timeline, checklists, anexos, etiquetas, membros) + its data layer.
 *
 * MOVED from social-wiring's lead card
 * (`products/social-wiring/frontend/src/components/card/*`,
 * `hooks/useCardHub.ts`) per
 * `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * (Slice C). Backend twin: `noctusai_lib.domain.card_hub` (Slice A).
 */
export { CardHubDialog } from "./CardHubDialog";
export type {
  CardHubDialogProps,
  CardHubActivityProps,
  CardHubRenderCtx,
  CardSubpage,
} from "./CardHubDialog";

export { CardSidebarNav, RAIL_LARGURA_FECHADA } from "./CardSidebarNav";
export type { CardSidebarNavItem, CardSidebarNavProps } from "./CardSidebarNav";

export {
  Timeline,
  DEFAULT_TIMELINE_RENDERERS,
  GENERIC_TIMELINE_RENDERERS,
} from "./Timeline";
export type { TimelineProps, TimelineKindRenderer, TimelineRenderers } from "./Timeline";

export { CardHubFace, resolveDueState } from "./CardHubFace";
export type { CardHubFaceProps } from "./CardHubFace";

export { GeralSubpage, GeralActions } from "./GeralSubpage";
export type {
  GeralSubpageProps,
  GeralSubpageSlots,
  GeralActionsProps,
  GeralPopoverKey,
} from "./GeralSubpage";

export { DescricaoSection } from "./DescricaoSection";
export type { DescricaoSectionProps } from "./DescricaoSection";

export { ChecklistsSection, ChecklistBlock } from "./ChecklistsSection";
export type { ChecklistsSectionProps, ChecklistBlockProps } from "./ChecklistsSection";

export { ComentarioComposer } from "./ComentarioComposer";
export type { ComentarioComposerProps } from "./ComentarioComposer";

export { AnexosSection } from "./AnexosSection";
export type { AnexosSectionProps } from "./AnexosSection";

export { ChecklistExtrasSection } from "./ChecklistExtrasSection";
export type { ChecklistExtrasSectionProps } from "./ChecklistExtrasSection";

export { CollapsibleSection } from "./CollapsibleSection";
export type { CollapsibleSectionProps } from "./CollapsibleSection";

export { TooltipIconButton, TooltipCaption } from "./TooltipIconButton";
export type { TooltipIconButtonProps, TooltipCaptionProps } from "./TooltipIconButton";

export { TokenCheckbox } from "./TokenCheckbox";
export type { TokenCheckboxProps } from "./TokenCheckbox";

export { EtiquetasPopover } from "./popovers/EtiquetasPopover";
export type { EtiquetasPopoverProps } from "./popovers/EtiquetasPopover";
export { MembrosPopover } from "./popovers/MembrosPopover";
export type { MembrosPopoverProps } from "./popovers/MembrosPopover";
export { ChecklistDialog } from "./popovers/ChecklistDialog";
export type { ChecklistDialogProps } from "./popovers/ChecklistDialog";

export { formatBytes, formatarDataISO, baixarArquivo } from "./format";

export { useSheetLayout, SHEET_MEDIA_QUERY } from "./useSheetLayout";

export {
  createCardHubHooks,
  cardHubLoadingState,
  flattenTimeline,
} from "./createCardHubHooks";
export type { CardHubHooks, CardHubApi, CardHubDescriptor } from "./createCardHubHooks";

export type * from "./types";
