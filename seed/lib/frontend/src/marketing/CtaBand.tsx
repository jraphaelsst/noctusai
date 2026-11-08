import { Card } from "../design-system/ui/FormControls";
import { cn } from "../utils";
import { Reveal } from "./primitives";
import { ActionLinks, sectionClass, wrapClass } from "./shared";
import type { LandingAction } from "./shared";

export interface CtaBandProps {
  id?: string;
  title: string;
  description?: string;
  actions: LandingAction[];
  /** "inverse" = the card is a dark band on the sidebar tokens (outline CTAs re-tone). Default "default". */
  variant?: "default" | "inverse";
}

/** Closing call-to-action, drawn as a card (one button family across the page). */
export function CtaBand({ id = "contato", title, description, actions, variant = "default" }: CtaBandProps) {
  const inverse = variant === "inverse";
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={sectionClass}>
      <div className={wrapClass}>
        <Reveal>
          <Card
            className={cn(
              "flex flex-col items-start justify-between gap-6 p-6 sm:p-8 md:flex-row md:items-center",
              inverse && "border-sidebar-border bg-sidebar text-sidebar-foreground",
            )}
          >
            <div className="max-w-xl">
              <h2 id={`${id}-title`} className={`text-xl font-semibold tracking-tight ${inverse ? "text-sidebar-foreground" : "text-foreground"} sm:text-2xl`}>{title}</h2>
              {description ? <p className={`mt-2 ${inverse ? "text-sidebar-foreground/75" : "text-muted-foreground"}`}>{description}</p> : null}
            </div>
            <ActionLinks actions={actions} inverse={inverse} />
          </Card>
        </Reveal>
      </div>
    </section>
  );
}
