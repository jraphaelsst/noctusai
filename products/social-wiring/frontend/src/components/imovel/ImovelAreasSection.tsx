/**
 * ImovelAreasSection — CONTRACT § 5.5 "Áreas".
 *
 * `area_construida` is null on 99.9% of this tenant — omitted rather than
 * shown as "—", same call the page already made before this contract.
 * `frente`/`fundos` are linear (lot width/depth), not an area, so they use
 * `formatMetros` ("m"), never `formatArea` ("m²").
 */
import { Ruler } from "lucide-react";

import { formatArea, formatMetros } from "@/hooks/useImoveis";

import Fact from "./Fact";
import SectionCard from "./SectionCard";

export default function ImovelAreasSection({
  areaTotal,
  areaPrivativa,
  areaConstruida,
  areaTerreno,
  frente,
  fundos,
}: {
  areaTotal: number | null;
  areaPrivativa: number | null;
  areaConstruida: number | null;
  areaTerreno: number | null;
  frente: number | null;
  fundos: number | null;
}) {
  const nada =
    areaTotal === null &&
    areaPrivativa === null &&
    areaConstruida === null &&
    areaTerreno === null &&
    frente === null &&
    fundos === null;
  if (nada) return null;

  return (
    <SectionCard title="Áreas" editLabel="Editar áreas">
      {areaTotal !== null && (
        <Fact icon={<Ruler className="h-4 w-4" />} label="Área total" value={formatArea(areaTotal)} />
      )}
      {areaPrivativa !== null && (
        <Fact icon={<Ruler className="h-4 w-4" />} label="Área privativa" value={formatArea(areaPrivativa)} />
      )}
      {areaConstruida !== null && (
        <Fact icon={<Ruler className="h-4 w-4" />} label="Área construída" value={formatArea(areaConstruida)} />
      )}
      {areaTerreno !== null && (
        <Fact icon={<Ruler className="h-4 w-4" />} label="Área do terreno" value={formatArea(areaTerreno)} />
      )}
      {frente !== null && (
        <Fact icon={<Ruler className="h-4 w-4" />} label="Frente" value={formatMetros(frente)} />
      )}
      {fundos !== null && (
        <Fact icon={<Ruler className="h-4 w-4" />} label="Fundos" value={formatMetros(fundos)} />
      )}
    </SectionCard>
  );
}
