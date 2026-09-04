/**
 * ImovelValoresSection — CONTRACT § 5.3 "Valores e custos".
 *
 * Venda/locação repeat the compact header display on purpose: the header is
 * the summary, this is the ledger. The monthly-cost line is DERIVED
 * (condomínio + IPTU/12), so it only renders when BOTH source values exist
 * — a half-derived total would understate the real monthly cost, which is
 * worse than not showing one.
 */
import { CircleDollarSign } from "lucide-react";

import { formatValor } from "@/hooks/useImoveis";

import Fact from "./Fact";
import SectionCard from "./SectionCard";

export default function ImovelValoresSection({
  valorVenda,
  valorLocacao,
  valorCondominio,
  valorIptu,
}: {
  valorVenda: number | null;
  valorLocacao: number | null;
  valorCondominio: number | null;
  valorIptu: number | null;
}) {
  const nada =
    valorVenda === null &&
    valorLocacao === null &&
    valorCondominio === null &&
    valorIptu === null;
  if (nada) return null;

  const custoMensal =
    valorCondominio !== null && valorIptu !== null
      ? valorCondominio + valorIptu / 12
      : null;

  return (
    <SectionCard title="Valores e custos" editLabel="Editar valores">
      {valorVenda !== null && (
        <Fact icon={<CircleDollarSign className="h-4 w-4" />} label="Venda" value={formatValor(valorVenda)} />
      )}
      {valorLocacao !== null && (
        <Fact icon={<CircleDollarSign className="h-4 w-4" />} label="Locação" value={`${formatValor(valorLocacao)}/mês`} />
      )}
      {valorCondominio !== null && (
        <Fact icon={<CircleDollarSign className="h-4 w-4" />} label="Condomínio" value={`${formatValor(valorCondominio)}/mês`} />
      )}
      {valorIptu !== null && (
        <Fact icon={<CircleDollarSign className="h-4 w-4" />} label="IPTU" value={formatValor(valorIptu)} />
      )}
      {custoMensal !== null && (
        <Fact
          icon={<CircleDollarSign className="h-4 w-4" />}
          label="Custo mensal estimado"
          value={`${formatValor(custoMensal)}/mês`}
        />
      )}
    </SectionCard>
  );
}
