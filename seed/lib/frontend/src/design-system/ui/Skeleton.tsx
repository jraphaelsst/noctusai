/**
 * Skeleton — canonical loading-placeholder primitive.
 *
 * Formalizes the `animate-pulse bg-muted` block that was hand-rolled
 * independently in `charts/ChartCard.tsx`, `components/PageSkeleton.tsx`,
 * `components/kanban/KanbanBoard.tsx`, `design-system/integrations/IntegrationCard.tsx`,
 * `ClientCredentialPanel.tsx`, and `design-system/chat/ChatWindow.tsx` (N≥5 —
 * the recurrence rule says formalize, not add a 6th copy). See
 * `products/social-wiring/projects/leads-module-PROJECT.md` for the observed
 * bug this closes: a hand-rolled `"Carregando..."` TEXT block (or, worse, a
 * stale empty-state message) rendered while data was still loading — a lie,
 * since it tells the user there is no data when the truth is "not known yet."
 *
 * Two things every consumer must get right, both handled here:
 *   1. Accessibility — a single loading REGION should announce ONE
 *      "Carregando" to assistive tech, not once per decorative block. Set
 *      `announce={false}` on every repeat except the one that should speak
 *      (see `TableSkeleton` for the canonical multi-block usage).
 *   2. `prefers-reduced-motion` — a pulsing page is an accessibility
 *      problem for vestibular-disorder users. Detected via `matchMedia` at
 *      mount (not a pure CSS `motion-reduce:` variant) so the suppression
 *      is verifiable in tests, not just trusted to ship correctly in CSS.
 */
import { useEffect, useState, type CSSProperties } from "react";
import { cn } from "../../utils";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/** Never throws — environments without `matchMedia` (old jsdom, SSR) fall back to `null`. */
function safeMatchMedia(query: string): MediaQueryList | null {
  try {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return null;
    return window.matchMedia(query);
  } catch {
    return null;
  }
}

/** Reads the live `prefers-reduced-motion` media feature; degrades to `false` (motion OK) when unavailable. */
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => safeMatchMedia(REDUCED_MOTION_QUERY)?.matches ?? false);

  useEffect(() => {
    const mql = safeMatchMedia(REDUCED_MOTION_QUERY);
    if (!mql) return undefined;

    const handleChange = (event: MediaQueryListEvent) => setReduced(event.matches);

    // Modern API.
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", handleChange);
      return () => mql.removeEventListener("change", handleChange);
    }
    // Legacy Safari fallback.
    if (typeof mql.addListener === "function") {
      mql.addListener(handleChange);
      return () => mql.removeListener(handleChange);
    }
    return undefined;
  }, []);

  return reduced;
}

export type SkeletonRounded = "sm" | "md" | "lg" | "full";

const ROUNDED_CLASS: Record<SkeletonRounded, string> = {
  sm: "rounded-sm",
  md: "rounded-md",
  lg: "rounded-lg",
  full: "rounded-full",
};

export interface SkeletonProps {
  className?: string;
  /** Fixed width — number is treated as px, string passed through verbatim (e.g. "100%"). */
  width?: number | string;
  /** Fixed height — number is treated as px, string passed through verbatim. */
  height?: number | string;
  rounded?: SkeletonRounded;
  /**
   * When `true` (default), this block IS the loading region's single
   * `role="status"` announcement. Set `false` on every other repeated
   * placeholder in the same region so screen readers hear "Carregando"
   * once, not once per block.
   */
  announce?: boolean;
  /** Accessible label used when `announce` is true. Default "Carregando". */
  label?: string;
}

export function Skeleton({
  className,
  width,
  height,
  rounded = "md",
  announce = true,
  label = "Carregando",
}: SkeletonProps) {
  const prefersReducedMotion = usePrefersReducedMotion();

  const style: CSSProperties = {};
  if (width !== undefined) style.width = width;
  if (height !== undefined) style.height = height;

  return (
    <div
      role={announce ? "status" : undefined}
      aria-label={announce ? label : undefined}
      aria-hidden={announce ? undefined : true}
      style={style}
      className={cn("bg-muted", !prefersReducedMotion && "animate-pulse", ROUNDED_CLASS[rounded], className)}
    />
  );
}
