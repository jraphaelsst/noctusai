/**
 * ImovelComodidadesSection — CONTRACT § 5.8 "Comodidades".
 *
 * Three distinct groups, per CONTRACT § 3 and § 5:
 *   1. Amenities the imóvel HAS (`caracteristicas`, "Sim" only) — prominent.
 *   2. `orientacao_solar` — NOT an amenity (Norte/Sul/Leste/Oeste), so it
 *      gets its own group rather than being mixed back into the chip list
 *      the backend already split it out of.
 *   3. Amenities it does NOT have — collapsed behind a disclosure so the
 *      card isn't dominated by negatives.
 */
import { ChevronDown, Compass } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

import { caracteristicaLabel, caracteristicasAusentes } from "@/hooks/useImoveis";

import SectionCard from "./SectionCard";

function orientacaoLabel(valor: string): string {
  const limpo = valor.trim().toLowerCase();
  return limpo.charAt(0).toUpperCase() + limpo.slice(1);
}

export default function ImovelComodidadesSection({
  caracteristicas,
  orientacaoSolar,
}: {
  caracteristicas: string[];
  orientacaoSolar: string[];
}) {
  if (caracteristicas.length === 0 && orientacaoSolar.length === 0) return null;

  const ausentes = caracteristicasAusentes(caracteristicas);

  return (
    <SectionCard
      title="Comodidades"
      editLabel="Editar comodidades"
      contentClassName="space-y-4"
    >
      {caracteristicas.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">
            Possui ({caracteristicas.length})
          </p>
          <div className="flex flex-wrap gap-2">
            {caracteristicas.map((slug) => (
              <Badge key={slug} variant="secondary">
                {caracteristicaLabel(slug)}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {orientacaoSolar.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Orientação solar</p>
          <div className="flex flex-wrap gap-2">
            {orientacaoSolar.map((valor) => (
              <Badge key={valor} variant="outline" className="gap-1">
                <Compass className="h-3 w-3" />
                {orientacaoLabel(valor)}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {ausentes.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:underline"
            >
              <ChevronDown className="h-3 w-3" />
              Não possui ({ausentes.length})
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 flex flex-wrap gap-2">
            {ausentes.map((slug) => (
              <Badge key={slug} variant="outline" className="text-muted-foreground">
                {caracteristicaLabel(slug)}
              </Badge>
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}
    </SectionCard>
  );
}
