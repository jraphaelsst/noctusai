import { Link } from "react-router-dom";
import { CalendarClock, ArrowRight } from "lucide-react";

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

export default function Landing() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* ── Navbar ─────────────────────────────────────── */}
      <header className="h-16 border-b border-border bg-card px-4 sm:px-8 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <CalendarClock className="h-7 w-7 text-primary" />
          <span className="text-xl font-bold text-primary">
            Imobi Scheduling
          </span>
        </Link>
        <Link
          to="/login"
          className="inline-flex items-center justify-center h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          Entrar
        </Link>
      </header>

      {/* ── Hero ───────────────────────────────────────── */}
      <section className="py-20 sm:py-28 px-4 text-center bg-gradient-to-b from-primary/5 to-background flex-1 flex flex-col items-center justify-center">
        <div className="max-w-3xl mx-auto space-y-6">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 text-primary text-sm font-medium">
            <CalendarClock className="h-4 w-4" />
            NoctusAI Imobi Scheduling
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-foreground">
            A minimal NoctusAI product
          </h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Proves the entire shared stack works: authentication, layout,
            notifications, theme, and SSO.
          </p>
          <div className="flex items-center justify-center gap-3 pt-2">
            <Link
              to="/login"
              className="inline-flex items-center justify-center gap-2 h-11 px-6 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              Comecar Agora
              <ArrowRight className="h-4 w-4" />
            </Link>
            <a
              href={CORE_URL}
              className="inline-flex items-center justify-center h-11 px-6 rounded-md border border-input bg-background text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              Conhecer NoctusAI
            </a>
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────── */}
      <footer className="border-t bg-card py-8 px-4 mt-auto">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <CalendarClock className="h-5 w-5 text-primary" />
            <span className="font-semibold text-primary">
              Imobi Scheduling
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            {new Date().getFullYear()} NoctusAI. Todos os direitos reservados.
          </p>
        </div>
      </footer>
    </div>
  );
}
