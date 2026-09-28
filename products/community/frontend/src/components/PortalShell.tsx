/**
 * PortalShell — the page frame every member-portal screen uses: a calm,
 * readable column (larger type, generous spacing — the audience is women
 * 50+, mostly on the phone) with the care line as its footer
 * (ninho-vazio CONTRACT.md §Care line: "the portal footer … carry" it).
 */
import type { ReactNode } from "react";

import { LinhaDeCuidado } from "@/components/LinhaDeCuidado";

export interface PortalShellProps {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
}

export function PortalShell({ title, subtitle, children }: PortalShellProps) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-1 py-2 text-base leading-relaxed sm:px-4 sm:py-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{title}</h1>
        {subtitle ? <p className="text-lg text-muted-foreground">{subtitle}</p> : null}
      </header>
      {children}
      <footer className="pt-2">
        <LinhaDeCuidado className="text-base" />
      </footer>
    </div>
  );
}

/** A soft section card sized for reading, not scanning. */
export function PortalCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-border bg-card p-5 sm:p-6 ${className}`}>{children}</section>;
}

/** Big-target link styled as a button (≥44px tall). */
export const BOTAO_GRANDE =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-lg px-6 py-3 text-base font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";
export const BOTAO_PRIMARIO = `${BOTAO_GRANDE} bg-primary text-primary-foreground hover:bg-primary/90`;
export const BOTAO_SECUNDARIO = `${BOTAO_GRANDE} border border-input bg-background text-foreground hover:bg-accent`;
