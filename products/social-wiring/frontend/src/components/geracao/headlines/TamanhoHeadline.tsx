/**
 * Headline length: a RECOMMENDATION with a warning, never a block (owner decision 2026-10-11:
 * "not limitation, but recommendation and warning. not block with limitations").
 *
 * The threshold comes from the backend (`recomendado_max_texto` + the computed
 * `acima_recomendado` on every headline response), so the FE never hardcodes it. The only hard
 * bound is the storage cap `HEADLINE_TEXTO_MAX`.
 */
import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Headline } from "@/types/geracao";
import { HEADLINE_TEXTO_MAX } from "../labels";

const AMBAR = "border-warning/40 bg-warning-light text-warning-foreground hover:bg-warning-light";

export function textoAvisoTamanho(n: number, recomendado: number): string {
  return `Acima do recomendado (${n}/${recomendado} caracteres)`;
}

type ComTamanho = Pick<Headline, "texto" | "acima_recomendado" | "recomendado_max_texto">;

/** Non-blocking amber badge, rendered only when the backend flags the headline. */
export function AvisoTamanhoHeadline({ headline, className }: { headline: ComTamanho; className?: string }) {
  if (!headline.acima_recomendado) return null;
  const n = headline.texto.trim().length;
  return (
    <Badge
      variant="outline"
      role="status"
      data-testid="aviso-tamanho-headline"
      className={cn("w-fit gap-1 font-medium", AMBAR, className)}
    >
      <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden />
      {textoAvisoTamanho(n, headline.recomendado_max_texto)}
    </Badge>
  );
}

/**
 * Live counter for a headline text field. Amber past the recommendation (saving stays enabled);
 * red only past the storage cap. Without a known `recomendado` it counts against the cap alone.
 */
export function ContadorHeadline({ texto, recomendado }: { texto: string; recomendado?: number }) {
  const n = texto.trim().length;
  const acimaMaximo = n > HEADLINE_TEXTO_MAX;
  const acimaRecomendado = recomendado != null && n > recomendado;
  let msg: string;
  if (acimaMaximo) msg = `${n}/${HEADLINE_TEXTO_MAX} caracteres — acima do máximo permitido`;
  else if (acimaRecomendado) msg = `${textoAvisoTamanho(n, recomendado)} — você ainda pode salvar`;
  else if (recomendado != null) msg = `${n}/${recomendado} caracteres recomendados`;
  else msg = `${n}/${HEADLINE_TEXTO_MAX} caracteres`;
  return (
    <p
      aria-live="polite"
      data-testid="contador-headline"
      data-estado={acimaMaximo ? "maximo" : acimaRecomendado ? "acima" : "ok"}
      className={cn(
        "flex items-center gap-1 text-xs",
        acimaMaximo ? "text-destructive" : acimaRecomendado ? "text-warning-foreground" : "text-muted-foreground",
      )}
    >
      {acimaRecomendado && !acimaMaximo && <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden />}
      {msg}
    </p>
  );
}
