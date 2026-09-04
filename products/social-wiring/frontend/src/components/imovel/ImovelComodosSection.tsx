/**
 * ImovelComodosSection — CONTRACT § 5.4 "Cômodos".
 *
 * Counts (dormitórios/suítes/vagas/closet) use `formatCount` so a genuine 0
 * on a Terreno reads "0"; the boolean (banheiro social) uses `formatBool`
 * and is omitted entirely when null, per CONTRACT § 7 — null means the
 * field is hidden, not shown as "Não".
 *
 * `Lavabo`/`Copa`/`Escritorio` are DELIBERATELY not here — CONTRACT § 1's
 * correction: Vista shadows them behind `Caracteristicas` (our sync always
 * requests both, so the top-level fields read null forever). They surface
 * as amenity chips in § 5.8 "Comodidades" instead, where the same values
 * already live.
 */
import { Bath, BedDouble, Car, DoorClosed, Sofa } from "lucide-react";

import { formatBool, formatCount } from "@/hooks/useImoveis";

import Fact from "./Fact";
import SectionCard from "./SectionCard";

export default function ImovelComodosSection({
  dormitorios,
  suites,
  vagas,
  banheiroSocial,
  closet,
}: {
  dormitorios: number | null;
  suites: number | null;
  vagas: number | null;
  banheiroSocial: boolean | null;
  closet: number | null;
}) {
  const banheiroSocialLabel = formatBool(banheiroSocial);

  const nada =
    dormitorios === null &&
    suites === null &&
    vagas === null &&
    banheiroSocialLabel === null &&
    closet === null;
  if (nada) return null;

  return (
    <SectionCard title="Cômodos" editLabel="Editar cômodos">
      {dormitorios !== null && (
        <Fact icon={<BedDouble className="h-4 w-4" />} label="Dormitórios" value={formatCount(dormitorios)} />
      )}
      {suites !== null && <Fact icon={<Sofa className="h-4 w-4" />} label="Suítes" value={formatCount(suites)} />}
      {vagas !== null && <Fact icon={<Car className="h-4 w-4" />} label="Vagas" value={formatCount(vagas)} />}
      {banheiroSocialLabel !== null && (
        <Fact icon={<Bath className="h-4 w-4" />} label="Banheiro social" value={banheiroSocialLabel} />
      )}
      {closet !== null && (
        <Fact icon={<DoorClosed className="h-4 w-4" />} label="Closet" value={formatCount(closet)} />
      )}
    </SectionCard>
  );
}
