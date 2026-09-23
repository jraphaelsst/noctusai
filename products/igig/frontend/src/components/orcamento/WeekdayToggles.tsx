/**
 * Seven tap targets (S T Q Q S S D) editing an item's `dias_semana` bitmask.
 * 40px circles — a thumb, not a cursor, is the primary pointer (R0).
 */
import { cn } from "@noctusai/lib";

import { WEEKDAYS, temDia, toggleDia } from "@/lib/weekdays";

export interface WeekdayTogglesProps {
  value: number;
  onChange: (mask: number) => void;
  disabled?: boolean;
  /** Prefix for accessible names ("Post feed — Segunda"). */
  label?: string;
}

export function WeekdayToggles({ value, onChange, disabled, label }: WeekdayTogglesProps) {
  return (
    <div role="group" aria-label={label ? `Dias da semana — ${label}` : "Dias da semana"} className="flex gap-1">
      {WEEKDAYS.map((d) => {
        const ativo = temDia(value, d.bit);
        return (
          <button
            key={d.bit}
            type="button"
            aria-pressed={ativo}
            aria-label={d.nome}
            title={d.nome}
            disabled={disabled}
            onClick={() => onChange(toggleDia(value, d.bit))}
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-full border text-xs font-semibold transition-colors sm:h-8 sm:w-8",
              ativo
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-background text-muted-foreground hover:bg-muted",
              disabled && "cursor-not-allowed opacity-60",
            )}
          >
            {d.letra}
          </button>
        );
      })}
    </div>
  );
}
