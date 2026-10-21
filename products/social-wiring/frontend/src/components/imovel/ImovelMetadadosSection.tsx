/**
 * ImovelMetadadosSection — CONTRACT § 5.13 "Metadados".
 *
 * `dias_desde_atualizacao` is derived server-side from `vista_raw` (CONTRACT
 * § 3, `DataAtualizacaoDias`) — never surfaced before this section.
 */
import { CalendarClock, History, RefreshCw } from "lucide-react";

import { formatDate } from "@/lib/utils";

import Fact from "./Fact";
import SectionCard from "./SectionCard";

export default function ImovelMetadadosSection({
  dataCadastro,
  dataAtualizacao,
  diasDesdeAtualizacao,
  sincronizadoEm,
}: {
  dataCadastro: string | null;
  dataAtualizacao: string | null;
  diasDesdeAtualizacao: number | null;
  sincronizadoEm: string | null;
}) {
  const nada = !dataCadastro && !dataAtualizacao && !sincronizadoEm;
  if (nada) return null;

  const atualizacaoValor = dataAtualizacao
    ? diasDesdeAtualizacao !== null
      ? `${formatDate(dataAtualizacao)} (há ${diasDesdeAtualizacao} dia${diasDesdeAtualizacao === 1 ? "" : "s"})`
      : formatDate(dataAtualizacao)
    : null;

  return (
    <SectionCard
      title="Metadados"
      editLabel="Editar metadados"
      contentClassName="space-y-2 text-xs text-muted-foreground"
    >
      {dataCadastro && (
        <Fact
          icon={<CalendarClock className="h-4 w-4" />}
          label="Cadastrado em"
          value={formatDate(dataCadastro)}
        />
      )}
      {atualizacaoValor && (
        <Fact icon={<History className="h-4 w-4" />} label="Atualizado em" value={atualizacaoValor} />
      )}
      {sincronizadoEm && (
        <Fact
          icon={<RefreshCw className="h-4 w-4" />}
          label="Sincronizado em"
          value={new Date(sincronizadoEm).toLocaleString("pt-BR")}
        />
      )}
    </SectionCard>
  );
}
