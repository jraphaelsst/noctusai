import type { ReactNode } from "react";
import { wrapClass } from "./shared";

export interface FooterLink {
  label: string;
  /** Navigation target. Mutually exclusive with `onClick`. */
  href?: string;
  /** For actions that are not navigation (e.g. "Preferências de cookies"): rendered as a <button>. */
  onClick?: () => void;
}
export interface FooterColumn { heading: string; links: FooterLink[] }

export interface LandingFooterProps {
  brand: ReactNode;
  /** A string, or a node when part of it must link (e.g. "Um produto <a>NoctusAI</a>"). */
  tagline?: ReactNode;
  columns: FooterColumn[];
  copyright: string;
  id?: string;
}

const linkClass =
  "rounded-sm text-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function LandingFooter({ brand, tagline, columns, copyright, id = "sobre" }: LandingFooterProps) {
  return (
    <footer id={id} className="border-t border-border bg-card py-10">
      <div className={wrapClass}>
        <div className="grid gap-8 md:grid-cols-[1.5fr_repeat(4,1fr)]">
          <div>
            {brand}
            {tagline ? <p className="mt-3 max-w-xs text-sm text-muted-foreground">{tagline}</p> : null}
          </div>
          {columns.map((col, i) => {
            const hid = `${id}-h-${i}`;
            return (
              <nav key={col.heading} aria-labelledby={hid}>
                <h2 id={hid} className="mb-3 text-sm font-semibold text-foreground">{col.heading}</h2>
                <ul className="flex flex-col gap-2">
                  {col.links.map((l) => (
                    <li key={l.label}>
                      {l.onClick ? (
                        <button type="button" onClick={l.onClick} className={linkClass}>{l.label}</button>
                      ) : (
                        <a href={l.href} className={linkClass}>{l.label}</a>
                      )}
                    </li>
                  ))}
                </ul>
              </nav>
            );
          })}
        </div>
        <div className="mt-8 border-t border-border pt-4 text-xs text-muted-foreground">{copyright}</div>
      </div>
    </footer>
  );
}
