/**
 * FilterBar — composable filter shell (label + control slots, active-filter
 * chips with individual clear, a "limpar tudo" action, collapsed/expanded on
 * mobile). Built for the Leads "Base de Leads" sticky filter bar (§6 of
 * leads-module-PROJECT.md) and its canonical filter set (§5.1), but takes no
 * dependency on that domain — it is PRESENTATIONAL ONLY. Filter STATE
 * (selected values, the URL-query-string mirror, `useLeadsFilters()`-style
 * hooks) stays entirely with the consumer.
 *
 *   <FilterBar chips={activeChips} onClearAll={clearAll}>
 *     <Select ... /> <DateRangePicker ... /> <Input placeholder="Buscar" />
 *   </FilterBar>
 */
import { useState } from "react";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import { cn } from "../../utils";
import type { FilterBarProps } from "./types";

export function FilterBar({
  children,
  chips = [],
  onClearAll,
  clearAllLabel = "Limpar tudo",
  defaultCollapsed = false,
  className,
}: FilterBarProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const hasChips = chips.length > 0;

  return (
    <div className={cn("rounded-lg border border-border bg-card p-3", className)}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted sm:hidden"
          aria-expanded={!collapsed}
        >
          Filtros
          {collapsed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
        </button>
      </div>

      <div className={cn("flex-wrap items-center gap-2", collapsed ? "hidden sm:flex" : "flex")}>{children}</div>

      {hasChips && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-border pt-2">
          {chips.map((chip) => (
            <span
              key={chip.key}
              className="inline-flex items-center gap-1 rounded-full border border-muted-foreground/30 bg-muted px-2.5 py-0.5 text-xs text-muted-foreground"
            >
              {chip.label}
              <button
                type="button"
                onClick={chip.onClear}
                aria-label={`Remover filtro ${chip.label}`}
                className="rounded-full hover:text-foreground"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          {onClearAll && (
            <button
              type="button"
              onClick={onClearAll}
              className="text-xs font-medium text-primary underline-offset-2 hover:underline"
            >
              {clearAllLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
