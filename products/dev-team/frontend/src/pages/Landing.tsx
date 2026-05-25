import { Link } from "react-router-dom";
import { Bot, ArrowRight } from "lucide-react";
import { env } from "@noctusai/lib";

// canonical seed resolver (env.CORE_URL) — no hand-rolled localhost:5173
const CORE_URL = env.CORE_URL;

export default function Landing() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="h-16 border-b border-border bg-card px-4 sm:px-8 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <Bot className="h-7 w-7 text-primary" />
          <span className="text-xl font-bold text-primary">Dev Team</span>
        </Link>
        <Link
          to="/login"
          className="inline-flex items-center justify-center h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
        >
          Entrar <ArrowRight className="h-4 w-4 ml-1" />
        </Link>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-16">
        <div className="max-w-2xl text-center space-y-6">
          <h1 className="text-4xl sm:text-5xl font-bold text-foreground">
            Multi-agent dev team
          </h1>
          <p className="text-lg text-muted-foreground">
            Eleven specialists, three sub-teams. Measurable + customizable. Ready to fire.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Link
              to="/login"
              className="inline-flex items-center justify-center h-11 px-6 rounded-md bg-primary text-primary-foreground font-medium hover:bg-primary/90"
            >
              Sign in
            </Link>
            <a
              href={CORE_URL}
              className="inline-flex items-center justify-center h-11 px-6 rounded-md border border-border bg-background font-medium hover:bg-muted"
            >
              NoctusAI
            </a>
          </div>
        </div>
      </main>
    </div>
  );
}
