/**
 * Financeiro — `/financeiro` (community-m2-contract.md §Frontend), new.
 *
 * Two tabs (Assinaturas / Pagamentos) rather than one merged table: the
 * two backend resources have different filters, different vocabularies for
 * `estado`, and — per amendment P3 — different role visibility
 * (`/api/pagamentos` is admin-only; `/api/assinaturas` is admin+moderador
 * with a redacted field set for `moderador`). A single merged view would
 * have to reconcile both shapes on every row; two tabs let each table stay
 * exactly what its endpoint returns.
 *
 * `moderador` P3 redaction is NEVER assumed present: `assinatura_externa_id`
 * renders "—" when absent rather than indexing it unconditionally, and a
 * 403 on the Pagamentos tab renders the server's own `detail` (never a
 * generic placeholder, never a crash) — this is what "a moderator-shaped
 * payload not crashing the page" means in practice.
 *
 * Two loading signals, never `isLoading`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge, Button, Input, TableSkeleton, Dialog, DialogHeader, DialogBody, DialogFooter } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { EmptyState, ErrorState, Field, FormError, Select } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { formatBRLFromCents } from "@/lib/money";
import {
  useAssinaturas,
  useCancelarAssinatura,
  type Assinatura,
  type AssinaturaEstado,
} from "@/hooks/useAssinaturas";
import { usePagamentos, type Pagamento, type PagamentoEstado } from "@/hooks/usePagamentos";

function formatDateBR(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("pt-BR");
}

const ASSINATURA_ESTADO_LABELS: Record<AssinaturaEstado, string> = {
  iniciada: "Iniciada",
  ativa: "Ativa",
  inadimplente: "Inadimplente",
  pausada: "Pausada",
  cancelada: "Cancelada",
};

const PAGAMENTO_ESTADO_LABELS: Record<PagamentoEstado, string> = {
  pendente: "Pendente",
  pago: "Pago",
  falhou: "Falhou",
  estornado: "Estornado",
};

function assinaturaBadgeVariant(estado: AssinaturaEstado): BadgeVariant {
  switch (estado) {
    case "ativa":
      return "default";
    case "inadimplente":
    case "cancelada":
      return "destructive";
    default:
      return "outline";
  }
}

function pagamentoBadgeVariant(estado: PagamentoEstado): BadgeVariant {
  switch (estado) {
    case "pago":
      return "default";
    case "falhou":
    case "estornado":
      return "destructive";
    default:
      return "outline";
  }
}

type Tab = "assinaturas" | "pagamentos";

export default function Financeiro() {
  const [tab, setTab] = useState<Tab>("assinaturas");
  const [assinaturaEstado, setAssinaturaEstado] = useState<AssinaturaEstado | "">("");
  const [pagamentoEstado, setPagamentoEstado] = useState<PagamentoEstado | "">("");
  const [membroIdFiltro, setMembroIdFiltro] = useState("");
  const [cancelTarget, setCancelTarget] = useState<Assinatura | null>(null);

  const assinaturasParams = useMemo(
    () => ({
      estado: assinaturaEstado || undefined,
      membro_id: membroIdFiltro || undefined,
      page: 1,
      page_size: 50,
    }),
    [assinaturaEstado, membroIdFiltro],
  );
  const pagamentosParams = useMemo(
    () => ({
      estado: pagamentoEstado || undefined,
      membro_id: membroIdFiltro || undefined,
      page: 1,
      page_size: 50,
    }),
    [pagamentoEstado, membroIdFiltro],
  );

  const assinaturas = useAssinaturas(assinaturasParams);
  const pagamentos = usePagamentos(pagamentosParams);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Financeiro</h1>
        <p className="text-sm text-muted-foreground">Assinaturas e pagamentos da comunidade.</p>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Financeiro">
        <Button variant={tab === "assinaturas" ? "primary" : "outline"} size="sm" onClick={() => setTab("assinaturas")}>
          Assinaturas
        </Button>
        <Button variant={tab === "pagamentos" ? "primary" : "outline"} size="sm" onClick={() => setTab("pagamentos")}>
          Pagamentos
        </Button>
      </div>

      <div className="flex flex-wrap gap-3">
        <Input
          className="w-64"
          placeholder="Filtrar por ID do membro"
          value={membroIdFiltro}
          onChange={(e) => setMembroIdFiltro(e.target.value)}
          aria-label="Filtrar por ID do membro"
        />
        {tab === "assinaturas" ? (
          <Select
            className="w-56"
            value={assinaturaEstado}
            onChange={(e) => setAssinaturaEstado(e.target.value as AssinaturaEstado | "")}
            aria-label="Filtrar por estado da assinatura"
          >
            <option value="">Todos os estados</option>
            {(Object.keys(ASSINATURA_ESTADO_LABELS) as AssinaturaEstado[]).map((s) => (
              <option key={s} value={s}>
                {ASSINATURA_ESTADO_LABELS[s]}
              </option>
            ))}
          </Select>
        ) : (
          <Select
            className="w-56"
            value={pagamentoEstado}
            onChange={(e) => setPagamentoEstado(e.target.value as PagamentoEstado | "")}
            aria-label="Filtrar por estado do pagamento"
          >
            <option value="">Todos os estados</option>
            {(Object.keys(PAGAMENTO_ESTADO_LABELS) as PagamentoEstado[]).map((s) => (
              <option key={s} value={s}>
                {PAGAMENTO_ESTADO_LABELS[s]}
              </option>
            ))}
          </Select>
        )}
      </div>

      {tab === "assinaturas" ? (
        <AssinaturasTable query={assinaturas} onCancel={setCancelTarget} />
      ) : (
        <PagamentosTable query={pagamentos} />
      )}

      {cancelTarget && <CancelarAssinaturaDialog assinatura={cancelTarget} onClose={() => setCancelTarget(null)} />}
    </div>
  );
}

function AssinaturasTable({
  query,
  onCancel,
}: {
  query: ReturnType<typeof useAssinaturas>;
  onCancel: (a: Assinatura) => void;
}) {
  const { data, isPending, isFetching, error } = query;
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  if (showSkeleton) return <TableSkeleton rows={6} columns={6} />;
  if (error) return <ErrorState message={errorMessage(error)} />;
  if (!data || data.items.length === 0) {
    return (
      <EmptyState message="Nenhuma assinatura ainda. Assinaturas aparecem aqui após o primeiro checkout." />
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
      {/* lying-loading-ok: caption-only refresh hint, table stays mounted */}
      {isRefreshing && <p className="px-4 py-1 text-xs text-muted-foreground">Atualizando…</p>}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="px-4 py-3 font-medium">Membro</th>
            <th className="px-4 py-3 font-medium">Plano</th>
            <th className="px-4 py-3 font-medium">Gateway</th>
            <th className="px-4 py-3 font-medium">Método</th>
            <th className="px-4 py-3 font-medium">Estado</th>
            <th className="px-4 py-3 font-medium">Ativa desde</th>
            <th className="px-4 py-3 font-medium text-right">Ações</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((a) => (
            <tr key={a.id} className="border-b border-border last:border-0" data-testid={`assinatura-row-${a.id}`}>
              <td className="px-4 py-3 text-foreground">{a.membro_nome}</td>
              <td className="px-4 py-3 text-foreground">{a.plano_nome}</td>
              <td className="px-4 py-3 text-foreground capitalize">{a.gateway}</td>
              <td className="px-4 py-3 text-foreground capitalize">{a.metodo}</td>
              <td className="px-4 py-3">
                <Badge variant={assinaturaBadgeVariant(a.estado)}>{ASSINATURA_ESTADO_LABELS[a.estado]}</Badge>
              </td>
              <td className="px-4 py-3 text-foreground">{formatDateBR(a.ativa_em)}</td>
              <td className="px-4 py-3 text-right">
                {a.estado !== "cancelada" && (
                  <button
                    type="button"
                    className="text-sm bg-danger/10 text-danger rounded-md px-3 py-1.5 hover:bg-danger/20 transition-colors"
                    onClick={() => onCancel(a)}
                    data-testid={`assinatura-cancelar-${a.id}`}
                  >
                    Cancelar
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PagamentosTable({ query }: { query: ReturnType<typeof usePagamentos> }) {
  const { data, isPending, isFetching, error } = query;
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  if (showSkeleton) return <TableSkeleton rows={6} columns={6} />;
  // P3/A16: a `moderador` gets a strict 403 here — render the backend's own
  // `detail` verbatim, never a generic message and never a crash.
  if (error) return <ErrorState message={errorMessage(error)} />;
  if (!data || data.items.length === 0) {
    return <EmptyState message="Nenhum pagamento ainda. Pagamentos aparecem aqui após o primeiro checkout." />;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
      {isRefreshing && <p className="px-4 py-1 text-xs text-muted-foreground">Atualizando…</p>}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="px-4 py-3 font-medium">Membro</th>
            <th className="px-4 py-3 font-medium">Valor</th>
            <th className="px-4 py-3 font-medium">Método</th>
            <th className="px-4 py-3 font-medium">Estado</th>
            <th className="px-4 py-3 font-medium">Pago em</th>
            <th className="px-4 py-3 font-medium">Vencimento</th>
            <th className="px-4 py-3 font-medium">Fatura</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((p: Pagamento) => (
            <tr key={p.id} className="border-b border-border last:border-0" data-testid={`pagamento-row-${p.id}`}>
              <td className="px-4 py-3 text-foreground">{p.membro_nome}</td>
              <td className="px-4 py-3 text-foreground">{formatBRLFromCents(p.valor_centavos)}</td>
              <td className="px-4 py-3 text-foreground capitalize">{p.metodo}</td>
              <td className="px-4 py-3">
                <Badge variant={pagamentoBadgeVariant(p.estado)}>{PAGAMENTO_ESTADO_LABELS[p.estado]}</Badge>
              </td>
              <td className="px-4 py-3 text-foreground">{formatDateBR(p.pago_em)}</td>
              <td className="px-4 py-3 text-foreground">{formatDateBR(p.vencimento)}</td>
              <td className="px-4 py-3 text-foreground">
                {p.url_fatura ? (
                  <a href={p.url_fatura} target="_blank" rel="noreferrer" className="text-primary underline">
                    Ver fatura
                  </a>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CancelarAssinaturaDialog({ assinatura, onClose }: { assinatura: Assinatura; onClose: () => void }) {
  const [motivo, setMotivo] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const cancelar = useCancelarAssinatura();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    cancelar.mutate(
      { id: assinatura.id, motivo },
      {
        onSuccess: () => {
          toast.success("Assinatura cancelada.");
          onClose();
        },
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open onClose={onClose} title="Cancelar assinatura" className="max-w-md">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Cancelar assinatura de {assinatura.membro_nome}</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Motivo" required>
            <Input value={motivo} onChange={(e) => setMotivo(e.target.value)} required />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={cancelar.isPending}>
            Voltar
          </Button>
          <Button type="submit" variant="destructive" disabled={cancelar.isPending}>
            {cancelar.isPending ? "Cancelando..." : "Confirmar cancelamento"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
