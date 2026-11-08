import { ChevronLeft } from "lucide-react";

export const BACK_TO_CORE_LABEL = "Voltar ao NoctusAI";

/**
 * Sidebar-footer link back to core's dashboard. Icon-only on purpose (owner
 * decision 2026-11-08): the name lives in `aria-label` + `title`, the target is
 * 32px (WCAG 2.2 AA 2.5.8 needs >= 24px) and keyboard focus is visible.
 */
export function BackToCore({ href }: { href: string }) {
  return (
    <a
      href={href}
      aria-label={BACK_TO_CORE_LABEL}
      title={BACK_TO_CORE_LABEL}
      className="flex h-8 w-8 items-center justify-center rounded-md text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ChevronLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
    </a>
  );
}
