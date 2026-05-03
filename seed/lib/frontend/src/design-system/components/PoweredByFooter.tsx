/**
 * NoctusAI — "Technology by NoctusAI" Footer
 *
 * Two variants:
 * - sidebar: Small, subtle text for the bottom of the sidebar nav
 * - landing: Full footer bar for login/landing pages (dark background)
 */

interface PoweredByFooterProps {
  variant: "sidebar" | "landing";
}

export function PoweredByFooter({ variant }: PoweredByFooterProps) {
  if (variant === "sidebar") {
    return (
      <div className="pt-2 text-center">
        <a
          href="https://noctusai.com"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[10px] text-sidebar-foreground/40 hover:text-sidebar-foreground/60 transition-colors"
        >
          Technology by NoctusAI
        </a>
      </div>
    );
  }

  // landing variant
  const currentYear = new Date().getFullYear();

  return (
    <footer className="w-full bg-sidebar text-sidebar-foreground/60 py-4 px-6">
      <div className="max-w-md mx-auto flex flex-col items-center gap-1">
        <a
          href="https://noctusai.com"
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-medium text-sidebar-foreground/80 hover:text-sidebar-foreground transition-colors"
        >
          NoctusAI
        </a>
        <p className="text-xs text-sidebar-foreground/50">
          AI-powered digital products
        </p>
        <p className="text-[10px] text-sidebar-foreground/30 mt-1">
          &copy; {currentYear} NoctusAI. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
