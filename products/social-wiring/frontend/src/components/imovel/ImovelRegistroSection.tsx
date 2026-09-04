/**
 * ImovelRegistroSection — CONTRACT § 5.12 "Registro".
 *
 * `matricula_vista`, NOT `matricula` — `social_wiring.imovel_dados`
 * (migration 075) already owns a cartório-authored `matricula`. These are
 * two distinct `origem`s in the same schema, and `ImovelCartorioCard`
 * (rendered right beneath this section, unchanged) owns the cartório one.
 */
import { FileText, Hash } from "lucide-react";

import Fact from "./Fact";
import SectionCard from "./SectionCard";

export default function ImovelRegistroSection({
  matriculaVista,
  inscricaoMunicipal,
  codigoImobiliaria,
  referencia,
}: {
  matriculaVista: string | null;
  inscricaoMunicipal: string | null;
  codigoImobiliaria: string | null;
  referencia: string | null;
}) {
  const nada = !matriculaVista && !inscricaoMunicipal && !codigoImobiliaria && !referencia;
  if (nada) return null;

  return (
    <SectionCard title="Registro" editLabel="Editar registro" contentClassName="space-y-2">
      {matriculaVista && (
        <Fact icon={<FileText className="h-4 w-4" />} label="Matrícula (Vista)" value={matriculaVista} />
      )}
      {inscricaoMunicipal && (
        <Fact icon={<FileText className="h-4 w-4" />} label="Inscrição municipal" value={inscricaoMunicipal} />
      )}
      {codigoImobiliaria && (
        <Fact icon={<Hash className="h-4 w-4" />} label="Código na imobiliária" value={codigoImobiliaria} />
      )}
      {referencia && <Fact icon={<Hash className="h-4 w-4" />} label="Referência" value={referencia} />}
    </SectionCard>
  );
}
