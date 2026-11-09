import { ChevronDown } from "lucide-react";
import { Reveal } from "./primitives";
import { SectionHead, sectionClass, wrapClass } from "./shared";

export interface FaqItem { question: string; answer: string }

export interface FaqProps {
  id?: string;
  eyebrow?: string;
  title: string;
  items: FaqItem[];
}

/** Accessible FAQ on native <details>/<summary> (keyboard + screen reader for free, works without JS). */
export function Faq({ id = "faq", eyebrow, title, items }: FaqProps) {
  const titleId = `${id}-title`;
  return (
    <section id={id} aria-labelledby={titleId} className={sectionClass}>
      <div className={wrapClass}>
        <Reveal>
          <SectionHead eyebrow={eyebrow} title={title} titleId={titleId} />
          <div className="max-w-3xl divide-y divide-border rounded-lg border border-border bg-card">
            {items.map((it) => (
              <details key={it.question} className="group px-4 py-3">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-md text-sm font-medium text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                  {it.question}
                  <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
                </summary>
                <p className="mt-2 text-sm text-muted-foreground">{it.answer}</p>
              </details>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}
