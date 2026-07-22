/**
 * ClearFiltersButton — the "Limpar filtros" recovery action shown next to
 * every Leads error state (§6 of leads-module-PROJECT.md).
 *
 * URL-hydration validation (`useLeadsFilters`) drops malformed values before
 * they ever reach a request, but a VALID-shaped filter can still fail at
 * request time (e.g. a UUID for a source/corretor that has since been
 * deleted). Without this, the only recovery from a filter-caused error was
 * hunting for the small "Limpar tudo" chip in the sticky filter bar above —
 * this puts the fix right next to the failure.
 */
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface ClearFiltersButtonProps {
  onClick: () => void;
  className?: string;
}

export function ClearFiltersButton({ onClick, className }: ClearFiltersButtonProps) {
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={onClick}
      className={className}
      data-testid="leads-error-clear-filters"
    >
      <X className="mr-1.5 h-3.5 w-3.5" />
      Limpar filtros
    </Button>
  );
}
