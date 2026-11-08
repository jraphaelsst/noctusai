import { Card } from "../design-system/ui/FormControls";
import { Reveal } from "./primitives";
import { ActionLinks, sectionClass, wrapClass } from "./shared";
import type { LandingAction } from "./shared";

export interface CtaBandProps {
  id?: string;
  title: string;
  description?: string;
  actions: LandingAction[];
}

/** Closing call-to-action, drawn as a card (one button family across the page). */
export function CtaBand({ id = "contato", title, description, actions }: CtaBandProps) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={sectionClass}>
      <div className={wrapClass}>
        <Reveal>
          <Card className="flex flex-col items-start justify-between gap-6 p-6 sm:p-8 md:flex-row md:items-center">
            <div className="max-w-xl">
              <h2 id={`${id}-title`} className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">{title}</h2>
              {description ? <p className="mt-2 text-muted-foreground">{description}</p> : null}
            </div>
            <ActionLinks actions={actions} />
          </Card>
        </Reveal>
      </div>
    </section>
  );
}
