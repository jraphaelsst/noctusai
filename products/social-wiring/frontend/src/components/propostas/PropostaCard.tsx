/** PropostaCard — imóvel, valor, status badge, validade (CONTRACT §4.3). */
import { Badge } from "@/components/ui/badge";
import { exibirData, exibirMoeda } from "@/lib/moedaDecimal";
import { PROPOSTA_STATUS_LABELS, type Proposta, type PropostaStatus } from "@/types/propostas";

const STATUS_CLASS: Record<PropostaStatus, string> = {
  rascunho: "bg-muted text-muted-foreground",
  enviada: "bg-blue-100 text-blue-800",
  aceita: "bg-green-100 text-green-800",
  recusada: "bg-red-100 text-red-800",
  cancelada: "bg-zinc-200 text-zinc-700",
};

export function PropostaStatusBadge({ status }: { status: PropostaStatus }) {
  return (
    <Badge className={STATUS_CLASS[status]} data-testid={`proposta-status-${status}`}>
      {PROPOSTA_STATUS_LABELS[status]}
    </Badge>
  );
}

export function PropostaCard({ proposta, onClick }: { proposta: Proposta; onClick: () => void }) {
  const validade = exibirData(proposta.validade_ate);
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-between gap-3 rounded-md border bg-card px-3 py-2 text-left hover:bg-accent"
      data-testid={`proposta-card-${proposta.id}`}
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">
          {proposta.imovel.titulo ?? proposta.imovel.codigo}
          <span className="ml-2 text-xs text-muted-foreground">{proposta.imovel.codigo}</span>
        </p>
        <p className="truncate text-xs text-muted-foreground">
          {exibirMoeda(proposta.valor_proposto)}
          {validade ? ` · válida até ${validade}` : ""}
        </p>
      </div>
      <PropostaStatusBadge status={proposta.status} />
    </button>
  );
}
