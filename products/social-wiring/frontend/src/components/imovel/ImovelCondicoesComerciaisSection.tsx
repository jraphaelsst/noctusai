/**
 * ImovelCondicoesComerciaisSection — CONTRACT § 5.7 "Condições comerciais".
 */
import { ArrowLeftRight, Key, Landmark, Megaphone, Monitor, Repeat } from "lucide-react";

import { Badge } from "@/components/ui/badge";

import { formatBool } from "@/hooks/useImoveis";

import Fact from "./Fact";
import SectionCard from "./SectionCard";

const FINALIDADE_LABEL: Record<string, string> = {
  venda: "Venda",
  aluguel: "Aluguel",
};

export default function ImovelCondicoesComerciaisSection({
  aceitaPermuta,
  aceitaFinanciamento,
  exclusivo,
  chave,
  finalidades,
  exibirNoSite,
  destaqueWeb,
  superDestaqueWeb,
}: {
  aceitaPermuta: boolean | null;
  aceitaFinanciamento: boolean | null;
  exclusivo: boolean | null;
  chave: string | null;
  finalidades: string[];
  exibirNoSite: boolean | null;
  destaqueWeb: boolean | null;
  superDestaqueWeb: boolean | null;
}) {
  const permutaLabel = formatBool(aceitaPermuta);
  const financiamentoLabel = formatBool(aceitaFinanciamento);
  const exclusivoLabel = formatBool(exclusivo);
  const exibirNoSiteLabel = formatBool(exibirNoSite);
  const destaqueWebLabel = formatBool(destaqueWeb);
  const superDestaqueWebLabel = formatBool(superDestaqueWeb);

  const nada =
    permutaLabel === null &&
    financiamentoLabel === null &&
    exclusivoLabel === null &&
    !chave &&
    finalidades.length === 0 &&
    exibirNoSiteLabel === null &&
    destaqueWebLabel === null &&
    superDestaqueWebLabel === null;
  if (nada) return null;

  return (
    <SectionCard title="Condições comerciais" editLabel="Editar condições comerciais">
      {finalidades.length > 0 && (
        <div className="col-span-full flex flex-wrap items-center gap-2">
          {finalidades.map((f) => (
            <Badge key={f} variant="outline">
              {FINALIDADE_LABEL[f] ?? f}
            </Badge>
          ))}
        </div>
      )}
      {permutaLabel !== null && (
        <Fact icon={<ArrowLeftRight className="h-4 w-4" />} label="Aceita permuta" value={permutaLabel} />
      )}
      {financiamentoLabel !== null && (
        <Fact icon={<Landmark className="h-4 w-4" />} label="Aceita financiamento" value={financiamentoLabel} />
      )}
      {exclusivoLabel !== null && (
        <Fact icon={<Repeat className="h-4 w-4" />} label="Exclusivo" value={exclusivoLabel} />
      )}
      {chave && <Fact icon={<Key className="h-4 w-4" />} label="Chave" value={chave} />}
      {exibirNoSiteLabel !== null && (
        <Fact icon={<Monitor className="h-4 w-4" />} label="Exibir no site" value={exibirNoSiteLabel} />
      )}
      {destaqueWebLabel !== null && (
        <Fact icon={<Megaphone className="h-4 w-4" />} label="Destaque" value={destaqueWebLabel} />
      )}
      {superDestaqueWebLabel !== null && (
        <Fact icon={<Megaphone className="h-4 w-4" />} label="Super destaque" value={superDestaqueWebLabel} />
      )}
    </SectionCard>
  );
}
