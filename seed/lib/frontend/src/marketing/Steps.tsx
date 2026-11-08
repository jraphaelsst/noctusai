import { Card } from "../design-system/ui/FormControls";
import { Reveal } from "./primitives";
import { SectionHead, sectionClass, wrapClass } from "./shared";

export interface StepItem { title: string; description: string }

export interface StepsProps {
  id?: string;
  eyebrow?: string;
  title: string;
  description?: string;
  steps: StepItem[];
}

/** Numbered process steps ("01", "02", …) as an ordered list. */
export function Steps({ id = "sob-medida", eyebrow, title, description, steps }: StepsProps) {
  const titleId = `${id}-title`;
  return (
    <section id={id} aria-labelledby={titleId} className={sectionClass}>
      <div className={wrapClass}>
        <Reveal>
          <SectionHead eyebrow={eyebrow} title={title} titleId={titleId} description={description} />
          <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map((s, i) => (
              <li key={s.title} className="flex">
                <Card className="flex w-full flex-col gap-2 p-5">
                  <span aria-hidden="true" className="text-sm font-semibold text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
                  <h3 className="text-base font-semibold text-foreground">{s.title}</h3>
                  <p className="text-sm text-muted-foreground">{s.description}</p>
                </Card>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>
    </section>
  );
}
