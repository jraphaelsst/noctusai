/**
 * The cliente card — the seed `CardHubDialog`, the SAME organ the negócio
 * card uses (roadmap R9: "o card do cliente É o card do funil"), with the
 * cliente's subpage registry:
 *
 *   Geral                  seed spine (etiquetas, membros, descrição, anexos,
 *                          checklists) + the cliente summary in `afterTags`
 *   Dados                  the cliente's fields, editable; remover cliente
 *   Marcas                 N marcas (paleta, logo, tom, personas) + cofre
 *   Orçamentos & Contratos orçamentos (OrcamentoModal) + contratos (modalidade,
 *                          marcar assinado)
 *   Calendário             `CalendarioMes clienteId`
 *   Esteira                `EsteiraBoard clienteId`
 *   Financeiro             faturas do cliente
 *
 * Only the ACTIVE subpage renders (the organ's registry is thunked), so an
 * unopened tab fetches nothing.
 */
import { CalendarDays, FileText, KanbanSquare, Palette, UserRound, Wallet } from "lucide-react";
import { CardHubDialog, type CardSubpage } from "@noctusai/lib/components";
import { Badge, Skeleton } from "@noctusai/lib/design-system";

import { CalendarioMes } from "@/components/calendario/CalendarioMes";
import { useCardHubGeral } from "@/components/common/useCardHubGeral";
import { EsteiraBoard } from "@/components/esteira/EsteiraBoard";
import { MarcasSubpage } from "@/components/marca/MarcasSubpage";
import { useCliente, type Cliente } from "@/hooks/useClientes";
import { clienteCardHub as hub } from "@/hooks/useClienteCardHub";
import { describeError } from "@/lib/errors";
import { dataBR } from "@/lib/format";
import { ClienteDadosPanel } from "./ClienteDadosPanel";
import { ClienteFinanceiro } from "./ClienteFinanceiro";
import { ClienteOrcamentosContratos } from "./ClienteOrcamentosContratos";
import { STATUS_CLIENTE_LABEL, STATUS_CLIENTE_VARIANT } from "./status";

export type ClienteSubpageKey =
  | "geral"
  | "dados"
  | "marcas"
  | "orcamentos"
  | "calendario"
  | "esteira"
  | "financeiro";

export interface ClienteCardDialogProps {
  /** The open cliente's id (from the list click or the `?id=` deep link). */
  clienteId: string | null;
  /** The list row, when the list has it — shown while the detail loads. */
  clienteDaLista?: Cliente | null;
  onClose: () => void;
  onAbrirOrcamento: (orcamentoId: string) => void;
}

export function ClienteCardDialog({ clienteId, clienteDaLista, onClose, onAbrirOrcamento }: ClienteCardDialogProps) {
  const detalhe = useCliente(clienteId);
  const cliente = detalhe.cliente ?? clienteDaLista ?? null;
  const hubGeral = useCardHubGeral(hub, clienteId, {
    afterTags: cliente ? <ClienteResumo cliente={cliente} /> : null,
  });

  const carregando = (subpage: React.ReactNode) =>
    cliente ? (
      subpage
    ) : detalhe.isError ? (
      <p role="alert" className="text-sm text-destructive">
        {describeError(detalhe.error, "Não foi possível carregar o cliente.")}
      </p>
    ) : (
      <Skeleton className="h-40 w-full" />
    );

  const subpages: CardSubpage<ClienteSubpageKey>[] = [
    hubGeral.geral,
    {
      key: "dados",
      label: "Dados",
      icon: UserRound,
      render: () => carregando(cliente ? <ClienteDadosPanel cliente={cliente} onRemovido={onClose} /> : null),
    },
    {
      key: "marcas",
      label: "Marcas",
      icon: Palette,
      render: () => (clienteId ? <MarcasSubpage clienteId={clienteId} clienteNome={cliente?.nome ?? ""} /> : null),
    },
    {
      key: "orcamentos",
      label: "Orçamentos & Contratos",
      icon: FileText,
      render: () =>
        clienteId ? <ClienteOrcamentosContratos clienteId={clienteId} onAbrirOrcamento={onAbrirOrcamento} /> : null,
    },
    {
      key: "calendario",
      label: "Calendário",
      icon: CalendarDays,
      render: () => (clienteId ? <CalendarioMes clienteId={clienteId} /> : null),
    },
    {
      key: "esteira",
      label: "Esteira",
      icon: KanbanSquare,
      render: () => (clienteId ? <EsteiraBoard clienteId={clienteId} /> : null),
    },
    {
      key: "financeiro",
      label: "Financeiro",
      icon: Wallet,
      render: () => (clienteId ? <ClienteFinanceiro clienteId={clienteId} /> : null),
    },
  ];

  const notFound = detalhe.isError && (detalhe.error as { status?: number } | null)?.status === 404;

  return (
    <CardHubDialog<ClienteSubpageKey>
      open={!!clienteId}
      onClose={onClose}
      isLoading={hubGeral.showSkeleton}
      error={notFound ? null : hubGeral.error}
      notFound={notFound}
      nome={cliente?.nome ?? hubGeral.nome ?? "Cliente"}
      testId="cliente-card-dialog"
      headerActions={
        cliente ? (
          <Badge variant={STATUS_CLIENTE_VARIANT[cliente.status]}>{STATUS_CLIENTE_LABEL[cliente.status]}</Badge>
        ) : null
      }
      subpages={subpages}
      defaultSubpage="geral"
      activity={hubGeral.activity}
    />
  );
}

/** Geral slot: who the cliente is, at a glance. Editing lives in "Dados". */
function ClienteResumo({ cliente }: { cliente: Cliente }) {
  const linhas: [string, string | null][] = [
    ["Nicho", cliente.nicho],
    ["E-mail", cliente.email],
    ["Telefone", cliente.telefone],
    ["Origem", cliente.origem],
    ["Cliente desde", cliente.created_at ? dataBR(cliente.created_at) : null],
  ];
  const visiveis = linhas.filter(([, v]) => !!v);
  if (visiveis.length === 0) return null;
  return (
    <dl className="grid gap-2 rounded-lg border border-border p-3 text-sm sm:grid-cols-2" data-testid="cliente-resumo">
      {visiveis.map(([rotulo, valor]) => (
        <div key={rotulo} className="min-w-0">
          <dt className="text-xs text-muted-foreground">{rotulo}</dt>
          <dd className="truncate text-foreground">{valor}</dd>
        </div>
      ))}
    </dl>
  );
}
