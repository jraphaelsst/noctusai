import type { ReactNode } from "react";
import { Card } from "../design-system/ui/FormControls";
import { cn } from "../utils";
import { Reveal, Stagger } from "./primitives";
import { ActionLinks, LandingIcon, accentInverseTextClass, accentTextClass, linkButtonClass, wrapClass } from "./shared";
import type { LandingAction } from "./shared";

export interface HeroChip { label: string; href: string; icone?: string | null }
export interface HeroStat { value: string; label: string }

export interface HeroProps {
  eyebrow?: string;
  title: string;
  /** Second, emphasised half of the h1 (rendered inside the same heading). */
  titleEmphasis?: string;
  lede: string;
  actions: LandingAction[];
  /** Derived from the catalog by the caller (only "disponível" rows). Omitted when empty. */
  chips?: HeroChip[];
  chipsLabel?: string;
  /** Media slot (poster, illustration, 3D canvas). Rendered inside a card; omit for a text-only hero. */
  media?: ReactNode;
  /** Accessible description of the media, when it is informative. */
  mediaLabel?: string;
  id?: string;
  /**
   * "plain" (default) sits on `background`. "inverse" is a dark band on the sidebar tokens with a soft
   * primary glow (the always-dark product hero); the outline CTA and text re-tone for it.
   */
  variant?: "plain" | "inverse";
  /** Render `media` without the Card wrapper: the slot draws its own surface. Default false (Card). */
  bareMedia?: boolean;
  /**
   * Colour `titleEmphasis` (and the eyebrow) with the brand accent (`primary`; `primary-light` on dark and
   * inverse) instead of the muted default. Default false (core's look).
   */
  accentEmphasis?: boolean;
  /** Optional figures under the CTAs (`<dl>` of value + label). Omitted when empty. */
  stats?: HeroStat[];
  /**
   * "reveal" (default): the whole copy block fades in once. "staggered": eyebrow, title, lede, CTAs, chips
   * and stats enter one after another and the media scales in. Content is never prerendered hidden and
   * reduced motion disables both.
   */
  entrance?: "reveal" | "staggered";
}

/** Landing hero. Defaults reproduce the plain variant (the primary button is the app's own). */
export function Hero({
  eyebrow, title, titleEmphasis, lede, actions, chips, chipsLabel = "Produtos disponíveis", media, mediaLabel, id = "top",
  variant = "plain", bareMedia = false, accentEmphasis = false, stats, entrance = "reveal",
}: HeroProps) {
  const inverse = variant === "inverse";
  const accent = inverse ? accentInverseTextClass : accentTextClass;
  const emphasisClass = accentEmphasis ? accent : inverse ? "text-sidebar-foreground/70" : "text-muted-foreground";
  const mutedText = inverse ? "text-sidebar-foreground/75" : "text-muted-foreground";
  const strongText = inverse ? "text-sidebar-foreground" : "text-foreground";

  const parts: ReactNode[] = [];
  if (eyebrow) {
    parts.push(
      <span key="eyebrow" className={cn("mb-3 block text-xs font-semibold uppercase tracking-wide", accentEmphasis ? accent : mutedText)}>
        {eyebrow}
      </span>,
    );
  }
  parts.push(
    <h1 key="title" id={`${id}-title`} className={`text-3xl font-semibold tracking-tight ${strongText} sm:text-5xl`}>
      {title}
      {titleEmphasis ? <> <span className={emphasisClass}>{titleEmphasis}</span></> : null}
    </h1>,
    <p key="lede" className={`mt-4 max-w-xl text-base ${mutedText} sm:text-lg`}>{lede}</p>,
    <ActionLinks key="actions" actions={actions} className="mt-6" inverse={inverse} />,
  );
  if (chips && chips.length > 0) {
    parts.push(
      <ul key="chips" aria-label={chipsLabel} className="mt-6 flex flex-wrap gap-2">
        {chips.map((c) => (
          <li key={c.label}>
            <a href={c.href} className={linkButtonClass(inverse ? "outline-inverse" : "outline", "sm")}>
              <LandingIcon name={c.icone} className="h-4 w-4" />
              {c.label}
            </a>
          </li>
        ))}
      </ul>,
    );
  }
  if (stats && stats.length > 0) {
    parts.push(
      <dl key="stats" className="mt-8 flex flex-wrap gap-x-8 gap-y-4">
        {stats.map((s) => (
          <div key={s.label} className="flex flex-col-reverse">
            <dt className={cn("text-xs", mutedText)}>{s.label}</dt>
            <dd className={cn("text-2xl font-semibold tabular-nums", strongText)}>{s.value}</dd>
          </div>
        ))}
      </dl>,
    );
  }

  const staggered = entrance === "staggered";
  const labelProps = mediaLabel ? { role: "img", "aria-label": mediaLabel } : {};
  const mediaNode = media
    ? bareMedia
      ? <div {...labelProps}>{media}</div>
      : <Card className="flex min-h-[16rem] items-center justify-center overflow-hidden" {...labelProps}>{media}</Card>
    : null;

  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={cn("py-14 sm:py-20", inverse && "relative overflow-hidden bg-sidebar text-sidebar-foreground")}
    >
      {inverse ? (
        <div
          aria-hidden="true"
          data-hero-glow=""
          className="pointer-events-none absolute inset-x-[-20%] bottom-[-40%] h-[70%] bg-[radial-gradient(50%_60%_at_50%_100%,hsl(var(--primary)/0.32),transparent_70%)]"
        />
      ) : null}
      <div className={cn(wrapClass, "grid items-center gap-10", media && "lg:grid-cols-2", inverse && "relative")}>
        {staggered ? <Stagger gap={0.08} y={18} duration={0.6}>{parts}</Stagger> : <Reveal>{parts}</Reveal>}
        {mediaNode ? (
          <Reveal delay={staggered ? 0.2 : 0.15} {...(staggered ? { scale: 0.96, duration: 0.8 } : {})}>
            {mediaNode}
          </Reveal>
        ) : null}
      </div>
    </section>
  );
}
