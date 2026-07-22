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
