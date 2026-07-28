/**
 * Stage colour token → Tailwind classes.
 *
 * WHY A LOOKUP AND NOT THE STORED STRING
 * --------------------------------------
 * `cor` is user-editable. If it held a class string, a user (or anyone who can
 * write that row) would be injecting arbitrary classNames into every board —
 * an XSS-adjacent surface via arbitrary-value utilities, and a reliable way to
 * break the design system one stage at a time.
 *
 * So the column stores a TOKEN from a closed set (CHECK-constrained in
 * migration 042, re-validated in the API layer), and the mapping to classes
 * lives here. An unknown token degrades to the neutral default rather than
 * rendering nothing or crashing — a stage created by a newer client must still
 * be visible to an older one.
 */
import type { StageColor } from './types';

export interface StageColorClasses {
  /** Header text colour. */
  color: string;
  /** Header background tint. */
  bgColor: string;
  /** Header border. */
  borderColor: string;
  /** Solid swatch, for the colour picker. */
  swatch: string;
}

// TEXT COLOUR: `text-<token>`, never `text-<token>-foreground`.
//
// `-foreground` tokens are the colour meant to sit ON a SOLID fill of that
// token — light text for a solid primary button. These labels sit on a 10%
// TINT, which is nearly white, so `text-primary-foreground` rendered
// light-on-light and the stage name was effectively invisible. Confirmed in
// the browser on 2026-07-28: the "Proposta" and "Fechado" column headers and
// the cliente-detail stage badge were all unreadable.
//
// The solid token (`text-primary`) is the brand colour itself, which has real
// contrast against its own tint — and still differentiates the stages.
// Inherited from the ERP's old `ETAPAS_CONFIG`, so the bug predates the
// extraction; it is fixed here because the seed now owns it for every consumer.
export const STAGE_COLOR_CLASSES: Record<StageColor, StageColorClasses> = {
  primary: {
    color: 'text-primary',
    bgColor: 'bg-primary/10',
    borderColor: 'border-primary',
    swatch: 'bg-primary',
  },
  secondary: {
    color: 'text-secondary-foreground',
    bgColor: 'bg-secondary/10',
    borderColor: 'border-secondary',
    swatch: 'bg-secondary',
  },
  success: {
    color: 'text-success',
    bgColor: 'bg-success/10',
    borderColor: 'border-success',
    swatch: 'bg-success',
  },
  warning: {
    color: 'text-warning',
    bgColor: 'bg-warning/10',
    borderColor: 'border-warning',
    swatch: 'bg-warning',
  },
  destructive: {
    color: 'text-destructive',
    bgColor: 'bg-destructive/10',
    borderColor: 'border-destructive',
    swatch: 'bg-destructive',
  },
  // `secondary-foreground` and `muted-foreground` are the exceptions that are
  // already correct: both are DARK readable text tokens, not on-solid-fill
  // pairs.
  muted: {
    color: 'text-muted-foreground',
    bgColor: 'bg-muted/50',
    borderColor: 'border-muted',
    swatch: 'bg-muted',
  },
};

const FALLBACK = STAGE_COLOR_CLASSES.secondary;

/** Classes for a token, falling back to neutral for anything unrecognised. */
export function stageColorClasses(cor: string | null | undefined): StageColorClasses {
  if (!cor) return FALLBACK;
  return STAGE_COLOR_CLASSES[cor as StageColor] ?? FALLBACK;
}

/** The pickable tokens, in the order the editor should offer them. */
export const STAGE_COLOR_OPTIONS: StageColor[] = [
  'secondary',
  'primary',
  'warning',
  'success',
  'destructive',
  'muted',
];

/** Human labels for the roles, for the editor's role selector. */
export const STAGE_ROLE_LABELS: Record<string, string> = {
  proposta_aceite: 'Aceite de proposta',
  final: 'Etapa final',
};
