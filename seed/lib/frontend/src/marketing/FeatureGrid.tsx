import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import { Card } from "../design-system/ui/FormControls";
import { Reveal } from "./primitives";
import { LandingIcon, SectionHead, linkButtonClass, sectionClass, wrapClass } from "./shared";

export interface FeatureItem {
  title: string;
  description: string;
  /** Registered lucide icon name, or a node for a custom glyph. */
  icon?: string | ReactNode;
  cta?: { label: string; href: string };
}

export interface FeatureGridProps {
  id?: string;
  eyebrow?: string;
  title: string;
  description?: string;
  items: FeatureItem[];
  columns?: 3 | 4;
}

/** Compact grid of benefit/audience tiles with an optional per-tile link. */
export function FeatureGrid({ id = "audiencias", eyebrow, title, description, items, columns = 3 }: FeatureGridProps) {
  const titleId = `${id}-title`;
  return (
    <section id={id} aria-labelledby={titleId} className={sectionClass}>
      <div className={wrapClass}>
        <Reveal>
          <SectionHead eyebrow={eyebrow} title={title} titleId={titleId} description={description} />
          <ul className={`grid gap-4 sm:grid-cols-2 ${columns === 4 ? "lg:grid-cols-4" : "lg:grid-cols-3"}`}>
            {items.map((it) => (
              <li key={it.title} className="flex">
                <Card className="flex w-full flex-col gap-3 p-5 transition-shadow hover:shadow-md motion-reduce:transition-none">
                  {it.icon ? (
                    <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-muted text-foreground">
                      {typeof it.icon === "string" ? <LandingIcon name={it.icon} className="h-5 w-5" /> : it.icon}
                    </span>
                  ) : null}
                  <h3 className="text-base font-semibold text-foreground">{it.title}</h3>
                  <p className="text-sm text-muted-foreground">{it.description}</p>
                  {it.cta ? (
                    <div className="mt-auto pt-2">
                      <a href={it.cta.href} className={linkButtonClass("outline", "sm")}>
                        {it.cta.label}
                        <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                      </a>
                    </div>
                  ) : null}
                </Card>
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
    </section>
  );
}
