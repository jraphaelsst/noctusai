/**
 * Cobranças -- the month summary (kept-after-inactivation rule) + every receivable with the gateway status banner.
 *
 * Two loading signals only (never `isLoading`): `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 * Writes (re-queue, extra charge) are offered to org admins; the server enforces them again.
 */
import { useState } from "react";
import { format } from "date-fns";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader, Field, Input, Select, Skeleton, TableSkeleton } from "@noctusai/lib/design-system";
import { RetryError } from "@noctusai/lib/organ-kit";
import { ClientSelect } from "@/components/ClientSelect";
import { ChargeStatusBanner } from "@/components/ChargeStatusBanner";
import {
  useCashFlow,
  useCharges,
  useCreateExtraCharge,
  useGatewayStatus,
  useRequeueCharge,
  type GenerationStatus,
} from "@/hooks/useFinancial";
import { ENTRY_STATUS_LABEL, GENERATION_STATUS_FILTER, formatCents, formatDay, formatReais } from "@/lib/charges";

const PAGE_SIZE = 25;

function SummaryCards({ month }: { month: string }) {
  const q = useCashFlow(month);
  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;
  if (showSkeleton) return <Skeleton className="h-20 w-full" />;
  if (q.isError && !q.data) return <RetryError message={`Erro ao carregar o resumo do mês: ${q.error.message}`} onRetry={() => void q.refetch()} retryLabel="Tentar novamente" />;
  if (!q.data) return null;
  const d = q.data;
  const cards = [
    { label: "Recebido", value: d.paid_revenues, tone: "text-green-700" },
    { label: "A receber", value: d.pending_revenues, tone: "text-foreground" },
    { label: "Em atraso", value: d.overdue_revenues, tone: "text-red-700" },
    { label: "Despesas pagas", value: d.paid_expenses, tone: "text-foreground" },
    { label: "Saldo (recebido − pago)", value: d.net, tone: d.net < 0 ? "text-red-700" : "text-foreground" },
  ];
  return (
    <div className="space-y-1">
      {isRefreshing ? <p className="text-xs text-muted-foreground" role="status">Atualizando…</p> : null}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {cards.map((c) => (
          <div key={c.label} className="rounded-lg border border-border bg-card p-3">
            <p className="text-xs text-muted-foreground">{c.label}</p>
            <p className={`text-lg font-semibold ${c.tone}`}>{formatReais(c.value)}</p>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground">
        Cobranças em aberto de clientes inativados só entram quando foram mantidas na inativação; canceladas nunca entram.
      </p>
    </div>
  );
}

function ExtraChargeDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateExtraCharge();
  const [clientId, setClientId] = useState<string | undefined>();
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [dueDate, setDueDate] = useState("");
  const cents = Math.round(Number(amount.replace(",", ".")) * 100);
  const valid = !!clientId && description.trim() !== "" && Number.isFinite(cents) && cents > 0 && dueDate !== "";

  const submit = () => {
    if (!valid || !clientId) return;
    create.mutate(
      { client_id: clientId, description: description.trim(), amount_cents: cents, due_date: dueDate },
      {
        onSuccess: () => {
          setClientId(undefined);
          setDescription("");
          setAmount("");
          setDueDate("");
          onClose();
        },
      },
    );
  };

  return (
    <Dialog open={open} onClose={onClose} title="Nova cobrança avulsa">
      <DialogHeader><h3 className="text-base font-semibold">Nova cobrança avulsa</h3></DialogHeader>
      <DialogBody>
        <div className="space-y-3">
          <ClientSelect value={clientId} onChange={setClientId} required noneLabel="Selecione o cliente" />
          <Field label="Descrição" required>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={255} placeholder="Ex.: Setup da conta de anúncios" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Valor (R$)" required>
              <Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0,00" />
            </Field>
            <Field label="Vencimento" required>
              <Input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
            </Field>
          </div>
        </div>
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button variant="outline" onClick={onClose}>Cancelar</Button>
        <Button onClick={submit} disabled={!valid || create.isPending}>{create.isPending ? "Criando…" : "Criar cobrança"}</Button>
      </DialogFooter>
    </Dialog>
  );
}

export function ChargesPanel({ isAdmin }: { isAdmin: boolean }) {
  const [month, setMonth] = useState(format(new Date(), "yyyy-MM"));
  const [status, setStatus] = useState<GenerationStatus | "">("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const gateway = useGatewayStatus();
  const charges = useCharges({ generation_status: status || undefined, page, page_size: PAGE_SIZE });
  const requeue = useRequeueCharge();

  const showSkeleton = charges.isPending && !charges.data;
  const isRefreshing = charges.isFetching && !!charges.data;
  const rows = charges.data?.items ?? [];
  const totalPages = Math.max(1, Math.ceil((charges.data?.total ?? 0) / PAGE_SIZE));

  return (
    <section className="space-y-4" aria-label="Cobranças">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Field label="Mês do resumo">
          <Input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} className="w-44" />
        </Field>
        {isAdmin ? <Button onClick={() => setCreating(true)}>Nova cobrança avulsa</Button> : null}
      </div>

      <SummaryCards month={month} />

      {gateway.data && !gateway.data.configured ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900" role="status">
          Nenhum gateway de cobrança configurado para esta organização: os recebíveis dos contratos ficam como recebíveis simples
          (sem boleto/PIX). Configure a chave do Asaas para gerar as cobranças automaticamente.
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Select aria-label="Filtrar por status do gateway" value={status} onChange={(e) => { setStatus(e.target.value as GenerationStatus | ""); setPage(1); }} className="w-64">
          {GENERATION_STATUS_FILTER.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
        {isRefreshing ? <span className="text-xs text-muted-foreground" role="status">Atualizando…</span> : null}
      </div>

      {showSkeleton ? (
        <TableSkeleton rows={6} columns={5} />
      ) : charges.isError && !charges.data ? (
        <RetryError message={`Erro ao carregar as cobranças: ${charges.error.message}`} onRetry={() => void charges.refetch()} retryLabel="Tentar novamente" />
      ) : rows.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          {status ? "Nenhuma cobrança com este status." : "Nenhuma cobrança ainda. Os recebíveis dos contratos aparecem aqui assim que forem gerados."}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Cliente</th>
                <th className="px-3 py-2">Descrição</th>
                <th className="px-3 py-2">Vencimento</th>
                <th className="px-3 py-2 text-right">Valor</th>
                <th className="px-3 py-2">Situação</th>
                <th className="px-3 py-2">Gateway</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.entry_id} className="border-t border-border align-top">
                  <td className="px-3 py-2">{c.client_name ?? "—"}</td>
                  <td className="px-3 py-2">{c.description}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {formatDay(c.due_date)}
                    {c.overdue ? <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 text-[11px] text-red-800">atrasada</span> : null}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">{formatCents(c.amount_cents)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{ENTRY_STATUS_LABEL[c.entry_status]}</td>
                  <td className="px-3 py-2 min-w-[16rem]">
                    <ChargeStatusBanner charge={c} onRequeue={isAdmin ? (id) => requeue.mutate(id) : undefined} requeuing={requeue.isPending} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 ? (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>Anterior</Button>
          <span>Página {page} de {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Próxima</Button>
        </div>
      ) : null}

      <ExtraChargeDialog open={creating} onClose={() => setCreating(false)} />
    </section>
  );
}
