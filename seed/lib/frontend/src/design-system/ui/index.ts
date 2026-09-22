/**
 * Design-system UI primitives — generic, reusable, token-aligned.
 *
 * These are the base-layer building blocks consumed by organ-level
 * components (IntegrationCard, IntegrationCardModal, etc.) and available
 * to any product that imports from `@noctusai/lib/design-system`.
 *
 * Exports:
 *   Badge         — pill-shaped status/label chip (4 variants)
 *   Button        — button primitive (primary / outline / ghost × sm / md / icon)
 *   Dialog        — inline modal primitive (backdrop + panel, no Radix dep)
 *   DialogHeader  — header sub-component for Dialog
 *   DialogBody    — scrollable body sub-component for Dialog
 *   DialogFooter  — footer sub-component for Dialog
 *   Input         — single-line text input (fully forwarded ref)
 *   HoverCard     — Radix-backed hover card (pre-existing)
 *   Skeleton      — canonical loading-placeholder block (announce + reduced-motion aware)
 *   TableSkeleton — table-shaped loading placeholder composed from Skeleton
 *   Card / Textarea / Select / Field / FormError / EmptyState / ErrorState
 *                 — small form/layout primitives (see FormControls.tsx)
 *   Popover / Checkbox / Switch / Avatar / ScrollArea / Progress
 *                 — Radix-backed card-hub primitives, SW shadcn-copy parity
 *                   (see popover.tsx / checkbox.tsx / switch.tsx / avatar.tsx /
 *                   scroll-area.tsx / progress.tsx)
 *   CardHubTextarea / CardHubSelect(+ sub-parts)
 *                 — Radix-shape siblings of Textarea/Select above, aliased to
 *                   avoid colliding with the native FormControls exports of
 *                   the same bare name (see textarea.tsx / select.tsx)
 *   CardHubButton / CardHubInput / CardHubDialog* / Tooltip
 *                 — card-hub Slice C additions: SW shadcn-copy parity for the
 *                   button, input, Radix dialog and tooltip the seed card hub
 *                   (`components/card-hub/`) is drawn with
 */
export { Badge } from "./Badge";
export type { BadgeProps, BadgeVariant } from "./Badge";

export { Button } from "./Button";
export type { ButtonProps, ButtonVariant, ButtonSize } from "./Button";

export { Dialog, DialogHeader, DialogBody, DialogFooter } from "./Dialog";
export type {
  DialogProps,
  DialogHeaderProps,
  DialogBodyProps,
  DialogFooterProps,
} from "./Dialog";

export { Input } from "./Input";
export type { InputProps } from "./Input";

export { HoverCard, HoverCardTrigger, HoverCardContent } from "./hover-card";

export { Skeleton } from "./Skeleton";
export type { SkeletonProps, SkeletonRounded } from "./Skeleton";

export { TableSkeleton } from "./TableSkeleton";
export type { TableSkeletonProps } from "./TableSkeleton";

export { Card, Textarea, Select, Field, FormError, EmptyState, ErrorState } from "./FormControls";
export type { CardProps, TextareaProps, SelectProps } from "./FormControls";

export { Popover, PopoverTrigger, PopoverAnchor, PopoverContent } from "./popover";

export { Checkbox } from "./checkbox";

export { Switch } from "./switch";

export { Avatar, AvatarImage, AvatarFallback } from "./avatar";

export { ScrollArea, ScrollBar } from "./scroll-area";

export { Progress } from "./progress";

export { Textarea as CardHubTextarea } from "./textarea";

export {
  Select as CardHubSelect,
  SelectGroup as CardHubSelectGroup,
  SelectValue as CardHubSelectValue,
  SelectTrigger as CardHubSelectTrigger,
  SelectContent as CardHubSelectContent,
  SelectLabel as CardHubSelectLabel,
  SelectItem as CardHubSelectItem,
  SelectSeparator as CardHubSelectSeparator,
  SelectScrollUpButton as CardHubSelectScrollUpButton,
  SelectScrollDownButton as CardHubSelectScrollDownButton,
} from "./select";

export { CardHubButton, cardHubButtonVariants } from "./card-hub-button";
export type { CardHubButtonProps, CardHubButtonVariant, CardHubButtonSize } from "./card-hub-button";

export { CardHubInput } from "./card-hub-input";

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "./tooltip";

export {
  Dialog as CardHubDialogRoot,
  DialogPortal as CardHubDialogPortal,
  DialogOverlay as CardHubDialogOverlay,
  DialogClose as CardHubDialogClose,
  DialogTrigger as CardHubDialogTrigger,
  DialogContent as CardHubDialogContent,
  DialogHeader as CardHubDialogHeader,
  DialogFooter as CardHubDialogFooter,
  DialogTitle as CardHubDialogTitle,
  DialogDescription as CardHubDialogDescription,
} from "./radix-dialog";
