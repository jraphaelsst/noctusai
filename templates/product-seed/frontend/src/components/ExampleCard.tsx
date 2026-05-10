/**
 * Example card — placeholder reusable component for the new product.
 *
 * Demonstrates the canonical design-token usage every product follows:
 *
 *   - `bg-card` / `border-border` / `text-foreground` / `text-muted-foreground`
 *     instead of hand-rolled `bg-white` + `border-gray-200`. Tokens flip
 *     automatically in dark mode + theme overrides — never use raw
 *     Tailwind colors.
 *   - `rounded-lg` + `p-4` matches the `pages/Example.tsx` empty-state
 *     card shape so the visual language is consistent.
 *   - `shadow-sm` for subtle elevation; reserve `shadow-md`+ for modals
 *     and floating panels.
 *
 * TODO(new-product): rename `ExampleCard` → your domain card
 * (`VideoCard`, `OrderRow`, `GoalTile`, …); accept the real domain
 * type as the prop; replace the placeholder fields with your real
 * data. Move to its own folder (`components/example/ExampleCard.tsx`
 * + sibling `ExampleCardSkeleton.tsx`) once you have variants.
 */
import { Boxes } from "lucide-react";

import { cn } from "@/lib/utils";

export interface ExampleCardProps {
  title: string;
  description?: string | null;
  className?: string;
  onClick?: () => void;
}

export function ExampleCard({
  title,
  description,
  className,
  onClick,
}: ExampleCardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card p-4 shadow-sm",
        "transition-colors hover:border-primary/50",
        onClick && "cursor-pointer",
        className,
      )}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className="flex items-start gap-3">
        <Boxes className="h-5 w-5 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-foreground">
            {title}
          </h3>
          {description ? (
            <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
              {description}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
