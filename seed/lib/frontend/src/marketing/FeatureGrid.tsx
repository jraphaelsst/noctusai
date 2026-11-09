import type { ReactNode } from "react";
import { ArrowRight, Check } from "lucide-react";
import { Card } from "../design-system/ui/FormControls";
import { cn } from "../utils";
import { Reveal } from "./primitives";
import { productBrandVars } from "./productBrand";
import type { ProductBrand } from "./productBrand";
import { LandingIcon, SectionHead, accentTextClass, linkButtonClass, sectionClass, wrapClass } from "./shared";

export interface FeatureItem {
  title: string;
  description: string;
  /** Registered lucide icon name, or a node for a custom glyph. */
  icon?: string | ReactNode;
  /** Outline button at the card foot (default look). */
  cta?: { label: string; href: string };
  /** Small chip above the title (e.g. "WhatsApp"). */
  tag?: string;
  /** Check-icon list under the description. */
  bullets?: string[];
  /**
   * Inline accent link at the card foot (not a button); the whole card becomes its click target.
   * `brand` re-colours it with ANOTHER product's accent (cross-product links). Ignored when `cta` is set.
   */
  link?: { label: string; href: string; brand?: ProductBrand };
}

export interface FeatureGridProps {
  id?: string;
  eyebrow?: string;
  title: string;
  description?: string;
  items: FeatureItem[];
  /** 2, 3 (default) or 4 columns from `lg` up. */
  columns?: 2 | 3 | 4;
  /** "large" = roomier cards with a bigger title. Default "default". */
  cardVariant?: "default" | "large";
  /**
   * Tint the eyebrow, icon chip and bullet checks with the brand accent (`primary`, `primary-light` on dark).
   * Default false (neutral, core's look).
   */
  accent?: boolean;
  /** Reveal each card as it enters the viewport, staggered by column. Default false (the grid reveals as one block). */
  revealItems?: boolean;
}

const COLS = { 2: "lg:grid-cols-2", 3: "lg:grid-cols-3", 4: "lg:grid-cols-4" } as const;

/** Compact grid of benefit/audience tiles with an optional tag, bullets and per-tile link. */
export function FeatureGrid({
  id = "audiencias", eyebrow, title, description, items, columns = 3,
  cardVariant = "default", accent = false, revealItems = false,
}: FeatureGridProps) {
  const titleId = `${id}-title`;
  const large = cardVariant === "large";

  const card = (it: FeatureItem) => (
    <Card
      className={cn(
        "flex w-full flex-col gap-3",
        large ? "p-6 sm:p-8" : "p-5",
        "transition-shadow hover:shadow-md motion-reduce:transition-none",
        it.link && "relative",
      )}
    >
      {it.icon ? (
        <span className={cn("inline-flex h-10 w-10 items-center justify-center rounded-md", accent ? `bg-primary/10 ${accentTextClass}` : "bg-muted text-foreground")}>
          {typeof it.icon === "string" ? <LandingIcon name={it.icon} className="h-5 w-5" /> : it.icon}
        </span>
      ) : null}
      {it.tag ? (
        <span className="self-start rounded-full border border-border px-2 py-0.5 text-xs font-semibold text-foreground">{it.tag}</span>
      ) : null}
      <h3 className={cn(large ? "text-xl sm:text-2xl" : "text-base", "font-semibold text-foreground")}>{it.title}</h3>
      <p className="text-sm text-muted-foreground">{it.description}</p>
      {it.bullets && it.bullets.length > 0 ? (
        <ul className="grid gap-1.5 text-sm text-foreground">
          {it.bullets.map((b) => (
            <li key={b} className="flex items-start gap-2">
              <Check className={cn("mt-0.5 h-4 w-4 shrink-0", accent ? accentTextClass : "text-muted-foreground")} aria-hidden="true" />
              {b}
            </li>
          ))}
        </ul>
      ) : null}
      {it.cta ? (
        <div className="mt-auto pt-2">
          <a href={it.cta.href} className={linkButtonClass("outline", "sm")}>
            {it.cta.label}
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
        </div>
      ) : it.link ? (
        <div className="mt-auto pt-3">
          <a
            href={it.link.href}
            style={it.link.brand ? productBrandVars(it.link.brand) : undefined}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-sm text-sm font-semibold underline-offset-4 hover:underline",
              "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ring-offset-background",
              "after:absolute after:inset-0 after:rounded-lg after:content-['']",
              accentTextClass,
            )}
          >
            {it.link.label}
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
        </div>
      ) : null}
    </Card>
  );

  const list = (
    <ul className={cn("grid gap-4 sm:grid-cols-2", COLS[columns])}>
      {items.map((it, i) => (
        <li key={it.title} className="flex">
          {revealItems ? (
            <Reveal className="flex w-full" delay={(i % columns) * 0.07} y={24} duration={0.55}>{card(it)}</Reveal>
          ) : card(it)}
        </li>
      ))}
    </ul>
  );

  return (
    <section id={id} aria-labelledby={titleId} className={sectionClass}>
      <div className={wrapClass}>
        {revealItems ? (
          <>
            <Reveal><SectionHead eyebrow={eyebrow} title={title} titleId={titleId} description={description} accent={accent} /></Reveal>
            {list}
          </>
        ) : (
          <Reveal>
            <SectionHead eyebrow={eyebrow} title={title} titleId={titleId} description={description} accent={accent} />
            {list}
          </Reveal>
        )}
      </div>
    </section>
  );
}
