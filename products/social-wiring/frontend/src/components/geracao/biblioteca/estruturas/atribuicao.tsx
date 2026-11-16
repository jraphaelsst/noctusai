/**
 * AI-draft attribution (legal requirement, wording fixed by the legal review) and the admin "unused for 24 months"
 * badge. Renders only where the server sent the field: `origem` reaches admins on the detail (never members, never
 * the list), `revisao_por_desuso` reaches admins only. No creator photo anywhere — handle + name only.
 */
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { EstruturaOrigem } from "@/types/estruturas";

export const ehGeradaPorIA = (origem: EstruturaOrigem | undefined): boolean => origem === "viral_auto";

export function fraseAtribuicaoIA(handle?: string | null): string {
  const h = handle?.trim().replace(/^@/, "");
  return h
    ? `Estrutura gerada por IA a partir de um vídeo público de @${h}; não é texto do criador.`
    : "Estrutura gerada por IA a partir de um vídeo público; não é texto do criador.";
}

/** Compact chip for cards; the full sentence is the tooltip and the accessible description. */
export function AtribuicaoIAChip({ origem, handle }: { origem: EstruturaOrigem | undefined; handle?: string | null }) {
  if (!ehGeradaPorIA(origem)) return null;
  const frase = fraseAtribuicaoIA(handle);
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge variant="outline" tabIndex={0} aria-label={`Gerada por IA. ${frase}`} data-testid="atribuicao-ia-chip">
            Gerada por IA
          </Badge>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">{frase}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/** The full sentence, for the detail page. */
export function AtribuicaoIAFrase({ origem, handle }: { origem: EstruturaOrigem | undefined; handle?: string | null }) {
  if (!ehGeradaPorIA(origem)) return null;
  return (
    <p className="rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm" data-testid="atribuicao-ia-frase">
      {fraseAtribuicaoIA(handle)}
    </p>
  );
}

export function formatarDataPtBR(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

/** Admin only: set when the Estrutura went 24 months without use. */
export function RevisaoDesusoBadge({ desde }: { desde?: string | null }) {
  if (!desde) return null;
  return (
    <Badge variant="outline" className="border-amber-500/50 bg-amber-500/10 font-normal text-amber-800 dark:text-amber-300">
      Revisão por desuso desde {formatarDataPtBR(desde)}
    </Badge>
  );
}
