import { useState, type MouseEvent } from "react";
import { ChevronLeft } from "lucide-react";

export const BACK_TO_CORE_LABEL = "Voltar ao NoctusAI";

export interface BackToCoreProps {
  href: string;
  /**
   * Voltar ends THIS product's session before leaving (SSO session lifecycle S5; the layout wires
   * `leaveProduct`). Runs on a plain primary click only: a modified or middle click opens core in a new
   * tab/window, so the product stays open here and nothing is revoked. Absent = a plain link.
   */
  onLeave?: () => Promise<void> | void;
}

/** A click the browser would open in a new tab/window (or not follow at all): never a "leave". */
function opensElsewhere(e: MouseEvent<HTMLAnchorElement>): boolean {
  return e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey;
}

/**
 * Sidebar-footer link back to core's dashboard. Icon-only on purpose (owner
 * decision 2026-11-08): the name lives in `aria-label` + `title`, the target is
 * 32px (WCAG 2.2 AA 2.5.8 needs >= 24px) and keyboard focus is visible.
 */
export function BackToCore({ href, onLeave }: BackToCoreProps) {
  const [leaving, setLeaving] = useState(false);
  const handleClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (!onLeave || opensElsewhere(e)) return;
    e.preventDefault();
    if (leaving) return;
    setLeaving(true);
    void onLeave();
  };
  return (
    <a
      href={href}
      onClick={handleClick}
      aria-label={BACK_TO_CORE_LABEL}
      aria-busy={leaving || undefined}
      title={BACK_TO_CORE_LABEL}
      className="flex h-8 w-8 items-center justify-center rounded-md text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ChevronLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
    </a>
  );
}
