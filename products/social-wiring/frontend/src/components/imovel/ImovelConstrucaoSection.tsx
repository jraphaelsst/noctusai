/**
 * ImovelConstrucaoSection — CONTRACT § 5.6 "Construção e estado".
 *
 * `ano_construcao` is stored as a plain year (coercion already turns a
 * literal "0" into NULL upstream — see the contract's coercion table), so
 * it uses `formatCount`, not `formatArea` — there is no unit to append.
 */
import { ArrowUpDown, Building, Calendar, Compass, DoorOpen, ShieldCheck } from "lucide-react";

import { formatBool, formatCount } from "@/hooks/useImoveis";

import Fact from "./Fact";
import SectionCard from "./SectionCard";

export default function ImovelConstrucaoSection({
  anoConstrucao,
  situacao,
  ocupacao,
  pavimentos,
  posicao,
  elevador,
  portaria,
}: {
  anoConstrucao: number | null;
  situacao: string | null;
  ocupacao: string | null;
  pavimentos: number | null;
  posicao: string | null;
  elevador: boolean | null;
  portaria: boolean | null;
}) {
  const elevadorLabel = formatBool(elevador);
  const portariaLabel = formatBool(portaria);

  const nada =
    anoConstrucao === null &&
    !situacao &&
    !ocupacao &&
    pavimentos === null &&
    !posicao &&
    elevadorLabel === null &&
    portariaLabel === null;
  if (nada) return null;

  return (
    <SectionCard title="Construção e estado" editLabel="Editar construção e estado">
      {anoConstrucao !== null && (
        <Fact icon={<Calendar className="h-4 w-4" />} label="Ano de construção" value={formatCount(anoConstrucao)} />
      )}
      {situacao && <Fact icon={<Building className="h-4 w-4" />} label="Situação" value={situacao} />}
      {ocupacao && <Fact icon={<DoorOpen className="h-4 w-4" />} label="Ocupação" value={ocupacao} />}
      {pavimentos !== null && (
        <Fact icon={<ArrowUpDown className="h-4 w-4" />} label="Pavimentos" value={formatCount(pavimentos)} />
      )}
      {posicao && <Fact icon={<Compass className="h-4 w-4" />} label="Posição" value={posicao} />}
      {elevadorLabel !== null && (
        <Fact icon={<ArrowUpDown className="h-4 w-4" />} label="Elevador" value={elevadorLabel} />
      )}
      {portariaLabel !== null && (
        <Fact icon={<ShieldCheck className="h-4 w-4" />} label="Portaria" value={portariaLabel} />
      )}
    </SectionCard>
  );
}
