/**
 * JourneyWizard — canonical multi-step "journey" organ: categorized short steps,
 * optional subtabs inside a step, progress bar ("Etapa X de N" + %), category rail,
 * validation gating, one-click skip for optional steps, keyboard navigation and
 * restrained CSS-only transitions (disabled under prefers-reduced-motion).
 *
 * Design-system tokens only — brand colours arrive through BrandProvider CSS vars.
 */
import * as React from "react";
import { Check } from "lucide-react";

import { cn } from "../utils";
import { Button } from "../design-system/ui/Button";

export interface JourneySubtab {
  id: string;
  title: string;
  content: React.ReactNode;
}

export interface JourneyContext {
  stepId: string;
  index: number;
  total: number;
  subtabId: string | null;
  next: () => void;
  back: () => void;
}

export interface JourneyStep {
  id: string;
  title: string;
  category: string;
  description?: string;
  content?: React.ReactNode | ((ctx: JourneyContext) => React.ReactNode);
  subtabs?: JourneySubtab[];
  /** true -> proceed; false or a string (the message) -> blocked. */
  validate?: () => boolean | string;
  optional?: boolean;
}

export interface JourneyWizardProps {
  steps: JourneyStep[];
  onComplete: (data: { completed: string[]; skipped: string[] }) => void;
  onStepChange?: (stepId: string, index: number) => void;
  /** Uncontrolled starting step. */
  initialStepId?: string;
  /** Controlled current step; pair with onStepChange. */
  currentStepId?: string;
  labels?: Partial<typeof DEFAULT_LABELS>;
  className?: string;
}

const DEFAULT_LABELS = {
  step: "Etapa",
  of: "de",
  back: "Voltar",
  next: "Continuar",
  finish: "Concluir",
  skip: "Pular etapa",
  optional: "Opcional",
  progress: "Progresso da jornada",
  steps: "Etapas",
};

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = React.useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false,
  );
  React.useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return reduced;
}

export function JourneyWizard({
  steps, onComplete, onStepChange, initialStepId, currentStepId, labels, className,
}: JourneyWizardProps) {
  const L = { ...DEFAULT_LABELS, ...labels };
  const reduced = usePrefersReducedMotion();
  const uid = React.useId();
  const [innerId, setInnerId] = React.useState(initialStepId ?? steps[0]?.id);
  const activeId = currentStepId ?? innerId;
  const index = Math.max(0, steps.findIndex((s) => s.id === activeId));
  const step = steps[index];
  const total = steps.length;

  const [done, setDone] = React.useState<string[]>([]);
  const [skipped, setSkipped] = React.useState<string[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const [subtabByStep, setSubtabByStep] = React.useState<Record<string, string>>({});
  const [direction, setDirection] = React.useState<1 | -1>(1);

  if (!step) return null;

  const subtabId = step.subtabs?.length
    ? (subtabByStep[step.id] ?? step.subtabs[0].id)
    : null;

  const goTo = (i: number) => {
    const target = steps[i];
    if (!target) return;
    setDirection(i >= index ? 1 : -1);
    setError(null);
    setInnerId(target.id);
    onStepChange?.(target.id, i);
  };

  const check = (): boolean => {
    const r = step.validate?.() ?? true;
    if (r === true) { setError(null); return true; }
    setError(typeof r === "string" ? r : "Revise os dados desta etapa para continuar.");
    return false;
  };

  const finishWith = (completed: string[], skip: string[]) =>
    onComplete({ completed, skipped: skip });

  const next = () => {
    if (!check()) return;
    const completed = done.includes(step.id) ? done : [...done, step.id];
    const skip = skipped.filter((s) => s !== step.id);
    setDone(completed);
    setSkipped(skip);
    if (index === total - 1) finishWith(completed, skip);
    else goTo(index + 1);
  };
  const back = () => index > 0 && goTo(index - 1);
  const skip = () => {
    const skip2 = skipped.includes(step.id) ? skipped : [...skipped, step.id];
    setSkipped(skip2);
    if (index === total - 1) finishWith(done, skip2);
    else goTo(index + 1);
  };

  // Forward jumps via the rail must not bypass validation of the current step.
  const jump = (i: number) => {
    if (i === index) return;
    if (i > index && !check()) return;
    goTo(i);
  };

  const onRailKey = (e: React.KeyboardEvent) => {
    const map: Record<string, number> = {
      ArrowRight: index + 1, ArrowDown: index + 1,
      ArrowLeft: index - 1, ArrowUp: index - 1,
      Home: 0, End: total - 1,
    };
    if (!(e.key in map)) return;
    e.preventDefault();
    const t = Math.min(total - 1, Math.max(0, map[e.key]));
    jump(t);
    requestAnimationFrame(() =>
      document.getElementById(`${uid}-tab-${steps[t].id}`)?.focus());
  };

  const ctx: JourneyContext = { stepId: step.id, index, total, subtabId, next, back };
  const body = typeof step.content === "function" ? step.content(ctx) : step.content;
  const activeSub = step.subtabs?.find((s) => s.id === subtabId);
  const pct = Math.round(((index + 1) / total) * 100);

  const categories: { name: string; items: { s: JourneyStep; i: number }[] }[] = [];
  steps.forEach((s, i) => {
    const last = categories[categories.length - 1];
    if (last && last.name === s.category) last.items.push({ s, i });
    else categories.push({ name: s.category, items: [{ s, i }] });
  });

  const motion = reduced ? "" : "transition-all duration-300 ease-out";
  const enter = reduced ? "" : "animate-in fade-in duration-300";

  return (
    <div
      className={cn("flex flex-col gap-6 text-foreground", className)}
      data-reduced-motion={reduced ? "true" : "false"}
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between text-sm">
          <span className="font-medium">{L.step} {index + 1} {L.of} {total}</span>
          <span className="text-muted-foreground">{pct}%</span>
        </div>
        <div
          role="progressbar"
          aria-label={L.progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          className="h-2 w-full overflow-hidden rounded-full bg-muted"
        >
          <div className={cn("h-full rounded-full bg-primary", motion)} style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div className="flex flex-col gap-6 md:flex-row">
        <div
          role="tablist"
          aria-label={L.steps}
          aria-orientation="vertical"
          onKeyDown={onRailKey}
          className="flex shrink-0 flex-col gap-4 md:w-60"
        >
          {categories.map((c) => (
            <div key={c.name} className="flex flex-col gap-1" role="presentation">
              <span className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {c.name}
              </span>
              {c.items.map(({ s, i }) => {
                const active = i === index;
                const complete = done.includes(s.id);
                return (
                  <button
                    key={s.id}
                    id={`${uid}-tab-${s.id}`}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    aria-controls={`${uid}-panel`}
                    tabIndex={active ? 0 : -1}
                    data-complete={complete ? "true" : "false"}
                    onClick={() => jump(i)}
                    className={cn(
                      "flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm",
                      motion,
                      active ? "bg-accent text-accent-foreground font-medium" : "text-muted-foreground hover:bg-muted",
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className={cn(
                        "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px]",
                        motion,
                        complete ? "border-success bg-success text-success-foreground"
                          : active ? "border-primary text-primary" : "border-border",
                      )}
                    >
                      {complete ? <Check className={cn("h-3 w-3", enter)} /> : i + 1}
                    </span>
                    <span className="truncate">{s.title}</span>
                    {s.optional && <span className="ml-auto text-[10px]">{L.optional}</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        <div className="min-w-0 flex-1">
          <div
            key={step.id}
            id={`${uid}-panel`}
            role="tabpanel"
            aria-labelledby={`${uid}-tab-${step.id}`}
            data-direction={direction}
            className={cn("flex flex-col gap-4 rounded-lg border border-border bg-card p-6 text-card-foreground", enter)}
          >
            <div>
              <h2 className="text-lg font-semibold">{step.title}</h2>
              {step.description && <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>}
            </div>

            {step.subtabs && step.subtabs.length > 0 && (
              <div role="tablist" aria-label={step.title} className="flex gap-1 border-b border-border">
                {step.subtabs.map((t) => {
                  const on = t.id === subtabId;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      role="tab"
                      aria-selected={on}
                      tabIndex={on ? 0 : -1}
                      onClick={() => setSubtabByStep((m) => ({ ...m, [step.id]: t.id }))}
                      onKeyDown={(e) => {
                        const subs = step.subtabs!;
                        const k = subs.findIndex((x) => x.id === t.id);
                        const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
                        if (!d) return;
                        e.stopPropagation();
                        e.preventDefault();
                        const n = subs[(k + d + subs.length) % subs.length];
                        setSubtabByStep((m) => ({ ...m, [step.id]: n.id }));
                      }}
                      className={cn(
                        "-mb-px border-b-2 px-3 py-2 text-sm",
                        motion,
                        on ? "border-primary text-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {t.title}
                    </button>
                  );
                })}
              </div>
            )}

            <div>{body}</div>
            {activeSub && <div key={activeSub.id} role="tabpanel" className={enter}>{activeSub.content}</div>}

            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          </div>

          <div className="mt-4 flex items-center justify-between gap-2">
            <Button variant="ghost" onClick={back} disabled={index === 0}>{L.back}</Button>
            <div className="flex items-center gap-2">
              {step.optional && <Button variant="outline" onClick={skip}>{L.skip}</Button>}
              <Button variant="primary" onClick={next}>{index === total - 1 ? L.finish : L.next}</Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
