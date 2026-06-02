/**
 * LandingFooter — minimal footer for the Core public landing page.
 *
 * Links to the three seed-mounted consent routes (unauthenticated, SPA-internal).
 * Kept local per user directive; do NOT hoist to seed/lib.
 */
import { Link } from "react-router-dom";

export function LandingFooter() {
  return (
    <footer className="border-t">
      <div className="max-w-6xl mx-auto px-4 py-6 flex flex-col items-center gap-3 sm:flex-row sm:justify-between text-sm text-muted-foreground">
        <span>© {new Date().getFullYear()} NoctusAI · Plataforma de Produtos Digitais AI-First</span>
        <nav aria-label="Links legais" className="flex items-center gap-4">
          <Link
            to="/consent"
            className="hover:text-foreground focus:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm transition-colors"
          >
            Central de Privacidade
          </Link>
          <Link
            to="/consent/privacy-policy"
            className="hover:text-foreground focus:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm transition-colors"
          >
            Política de Privacidade
          </Link>
          <Link
            to="/consent/terms-of-use"
            className="hover:text-foreground focus:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm transition-colors"
          >
            Termos de Uso
          </Link>
        </nav>
      </div>
    </footer>
  );
}
