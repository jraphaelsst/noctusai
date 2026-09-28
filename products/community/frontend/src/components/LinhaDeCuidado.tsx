/**
 * Linha de cuidado — the CVV line every member-facing and grupoterapia
 * screen carries (CONTRACT.md §Care line).
 *
 * The comment analysis behind this product found members writing about
 * wanting to die; this line is non-negotiable on those screens, so it is
 * one component rather than a string each page re-types.
 */
import { HeartHandshake } from "lucide-react";

import { cn } from "@/lib/utils";

export const TEXTO_LINHA_DE_CUIDADO =
  "Se estiver pesado demais, procure ajuda. CVV 188 — gratuito, 24 horas.";

export interface LinhaDeCuidadoProps {
  className?: string;
}

export function LinhaDeCuidado({ className }: LinhaDeCuidadoProps) {
  return (
    <p
      role="note"
      className={cn(
        "flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-sm text-muted-foreground",
        className,
      )}
    >
      <HeartHandshake className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>
        Se estiver pesado demais, procure ajuda.{" "}
        <a href="tel:188" className="font-medium text-foreground underline underline-offset-2">
          CVV 188
        </a>{" "}
        — gratuito, 24 horas.
      </span>
    </p>
  );
}
