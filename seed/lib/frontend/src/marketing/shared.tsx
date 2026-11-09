/**
 * Landing-organ shared pieces: the action type, link-styled buttons and the
 * section heading. Everything uses seed design tokens only (no raw colours).
 *
 * `linkButtonClass` mirrors the seed `Button` classes for `<a>` elements: the
 * seed Button renders a <button>, and a link that navigates must be an anchor
 * (never a button with an onClick), so the look is shared and the element differs.
 */
import type { ReactNode } from "react";
import {
  ArrowRight, Bot, BookOpen, Box, Brain, Briefcase, Building, Building2, Calendar, CalendarCheck, FileText,
  FlaskConical, GitMerge, Kanban, Lock, Megaphone, MessageCircle, Palette, Power, Recycle, Share2,
  ShieldCheck, ShoppingBag, Sprout, Store, Target, User, Users, UsersRound, Wallet, Wand,
  type LucideIcon,
} from "lucide-react";
import { cn } from "../utils";

export interface LandingAction {
  label: string;
  href: string;
  /** "primary" = filled, "outline" = bordered. */
  variant?: "primary" | "outline" | "ghost";
}

const base =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors " +
  "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ring-offset-background";
const variants = {
  primary: "bg-primary text-primary-foreground hover:bg-primary/90",
  outline: "border border-input bg-background hover:bg-accent",
  ghost: "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
  // Inverse band (sidebar tokens): the same families, re-toned for the dark surface.
  "outline-inverse": "border border-sidebar-border bg-transparent text-sidebar-foreground hover:bg-sidebar-accent",
  "ghost-inverse": "text-sidebar-foreground hover:bg-sidebar-accent",
};
const sizes = { sm: "h-7 px-3 text-xs", md: "h-8 px-4 text-sm", lg: "h-10 px-5 text-base" };

export function linkButtonClass(
  variant: keyof typeof variants = "outline",
  size: keyof typeof sizes = "md",
  extra?: string,
) {
  return cn(base, variants[variant], sizes[size], extra);
}

function inverseVariant(v: NonNullable<LandingAction["variant"]>, inverse: boolean): keyof typeof variants {
  if (!inverse || v === "primary") return v;
  return v === "ghost" ? "ghost-inverse" : "outline-inverse";
}

/** Accent text: `primary` on light, `primary-light` on dark (AA on both surfaces). */
export const accentTextClass = "text-primary dark:text-primary-light";
/** Accent text on an inverse (always-dark) band. */
export const accentInverseTextClass = "text-primary-light";

/** A row of CTA links; a `primary` one gets the trailing arrow. */
export function ActionLinks({ actions, className, inverse = false }: { actions: LandingAction[]; className?: string; inverse?: boolean }) {
  return (
    <div className={cn("flex flex-wrap gap-3", className)}>
      {actions.map((a) => (
        <a key={a.label + a.href} href={a.href} className={linkButtonClass(inverseVariant(a.variant ?? "outline", inverse), "lg", inverse ? "focus-visible:ring-offset-sidebar" : undefined)}>
          {a.label}
          {a.variant === "primary" ? <ArrowRight className="h-4 w-4" aria-hidden="true" /> : null}
        </a>
      ))}
    </div>
  );
}

export function SectionHead({
  eyebrow, title, titleId, description, accent = false,
}: { eyebrow?: string; title: string; titleId: string; description?: string; accent?: boolean }) {
  return (
    <div className="mb-8 max-w-2xl">
      {eyebrow ? (
        <span className={cn("mb-2 block text-xs font-semibold uppercase tracking-wide", accent ? accentTextClass : "text-muted-foreground")}>{eyebrow}</span>
      ) : null}
      <h2 id={titleId} className="text-2xl font-semibold tracking-tight text-foreground sm:text-4xl">{title}</h2>
      {description ? <p className="mt-3 text-base text-muted-foreground">{description}</p> : null}
    </div>
  );
}

/** Tailwind `grid`/`flex` utilities beat the `hidden` attribute; this restores it. */
export const HIDDEN_ATTR = "[&[hidden]]:hidden";

export const sectionClass = "py-12 sm:py-16";
export const wrapClass = "mx-auto w-full max-w-6xl px-4 sm:px-6";

// ---- icons by name (the `icone` column of public.products is a lucide name) ----
const ICONS: Record<string, LucideIcon> = {
  Building2, Wallet, Brain, CalendarCheck, Share2, Store, Bot, BookOpen, Sprout, Box,
  Palette, Recycle, UsersRound, ShoppingBag, User, Briefcase, ShieldCheck,
  // Product-landing additions (agents / social-wiring mockups).
  Power, FlaskConical, GitMerge, Target, Lock, MessageCircle, Kanban, Building, FileText,
  Megaphone, Wand, Users, Calendar,
};

/** Renders a registered lucide icon by name; an unknown name falls back to `Box`. */
export function LandingIcon({ name, className }: { name?: string | null; className?: string }): ReactNode {
  const Icon = (name && ICONS[name]) || Box;
  return <Icon className={className ?? "h-5 w-5"} aria-hidden="true" />;
}
