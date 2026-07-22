/**
 * MultiSelectPopover — small local control backing every multi-value
 * dimension in `LeadsFilterBar` (ano/mes/origem/corretor/tipo/tier/
 * empreendimento/regiao — §5.1). Not a design-system organ: this is a
 * page-local presentational primitive, one level below the seed `FilterBar`
 * shell (which is itself presentational-only and takes generic `children`).
 *
 *   <MultiSelectPopover label="Origem" options={sourceOptions}
 *     selected={filters.origem_id} onToggle={(v) => toggleMulti("origem_id", v)} />
 */
import { useState } from "react";
import { Check, ChevronDown, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export interface MultiSelectOption {
  value: string;
  label: string;
  /** Optional color swatch (e.g. a source's `cor`). */
  color?: string | null;
}

export interface MultiSelectPopoverProps {
  label: string;
  options: MultiSelectOption[];
  selected: string[];
  onToggle: (value: string) => void;
  emptyMessage?: string;
  testId?: string;
}

export function MultiSelectPopover({
  label,
  options,
  selected,
  onToggle,
  emptyMessage = "Nenhuma opção disponível.",
  testId,
}: MultiSelectPopoverProps) {
  const count = selected.length;
  const [search, setSearch] = useState("");

  const filteredOptions = search.trim()
    ? options.filter((o) => o.label.toLowerCase().includes(search.trim().toLowerCase()))
    : options;

  return (
    <Popover onOpenChange={(open) => !open && setSearch("")}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          data-testid={testId}
        >
          {label}
          {count > 0 && (
            <span className="rounded-full bg-primary px-1.5 text-[10px] font-semibold text-primary-foreground">
              {count}
            </span>
          )}
          <ChevronDown className="h-3.5 w-3.5 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-2" align="start">
        {options.length > 6 && (
          <div className="relative mb-1.5">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar..."
              className="h-8 pl-7 text-xs"
              data-testid={testId ? `${testId}-search` : undefined}
            />
          </div>
        )}
        <div className="max-h-72 space-y-0.5 overflow-y-auto">
          {options.length === 0 ? (
            <p className="px-2 py-3 text-center text-xs text-muted-foreground">
              {emptyMessage}
            </p>
          ) : filteredOptions.length === 0 ? (
            <p className="px-2 py-3 text-center text-xs text-muted-foreground" data-testid={testId ? `${testId}-no-results` : undefined}>
              Nenhum resultado para "{search}".
            </p>
          ) : (
            filteredOptions.map((option) => {
              const isSelected = selected.includes(option.value);
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onToggle(option.value)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted",
                    isSelected && "bg-muted/60",
                  )}
                  data-testid={testId ? `${testId}-option-${option.value}` : undefined}
                >
                  <span
                    className={cn(
                      "flex h-4 w-4 shrink-0 items-center justify-center rounded border border-border",
                      isSelected && "border-primary bg-primary text-primary-foreground",
                    )}
                  >
                    {isSelected && <Check className="h-3 w-3" />}
                  </span>
                  {option.color && (
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: option.color }}
                    />
                  )}
                  <span className="truncate">{option.label}</span>
                </button>
              );
            })
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
