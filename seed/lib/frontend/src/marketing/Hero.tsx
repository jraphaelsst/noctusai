import type { ReactNode } from "react";
import { Card } from "../design-system/ui/FormControls";
import { Reveal } from "./primitives";
import { ActionLinks, LandingIcon, linkButtonClass, wrapClass } from "./shared";
import type { LandingAction } from "./shared";

export interface HeroChip { label: string; href: string; icone?: string | null }

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
}

/** Landing hero, "plain" variant (on `background`, so the primary button is the app's own). */
export function Hero({
  eyebrow, title, titleEmphasis, lede, actions, chips, chipsLabel = "Produtos disponíveis", media, mediaLabel, id = "top",
}: HeroProps) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="py-14 sm:py-20">
      <div className={`${wrapClass} grid items-center gap-10 ${media ? "lg:grid-cols-2" : ""}`}>
        <Reveal>
          {eyebrow ? (
            <span className="mb-3 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">{eyebrow}</span>
          ) : null}
          <h1 id={`${id}-title`} className="text-3xl font-semibold tracking-tight text-foreground sm:text-5xl">
            {title}
            {titleEmphasis ? <> <span className="text-muted-foreground">{titleEmphasis}</span></> : null}
          </h1>
          <p className="mt-4 max-w-xl text-base text-muted-foreground sm:text-lg">{lede}</p>
          <ActionLinks actions={actions} className="mt-6" />
          {chips && chips.length > 0 ? (
            <ul aria-label={chipsLabel} className="mt-6 flex flex-wrap gap-2">
              {chips.map((c) => (
                <li key={c.label}>
                  <a href={c.href} className={linkButtonClass("outline", "sm")}>
                    <LandingIcon name={c.icone} className="h-4 w-4" />
                    {c.label}
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </Reveal>
        {media ? (
          <Reveal delay={0.15}>
            <Card
              className="flex min-h-[16rem] items-center justify-center overflow-hidden"
              {...(mediaLabel ? { role: "img", "aria-label": mediaLabel } : {})}
            >
              {media}
            </Card>
          </Reveal>
        ) : null}
      </div>
    </section>
  );
}
