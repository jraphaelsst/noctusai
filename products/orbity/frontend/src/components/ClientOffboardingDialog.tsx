/**
 * ClientOffboardingDialog -- inactivate a client WITHOUT silently dropping what it owes.
 *
 * Lists the client's open charges (pending + overdue); per charge the operator chooses Cancelar (default) or Manter. Kept
 * charges stay payable and keep counting in the cash flow; cancelled ones are cancelled (at the gateway too). The live
 * contracts are ended. One admin-only server operation does it all -- the result says exactly what is left if a step failed.
 */
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useConfirm } from "@noctusai/lib/components";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader, Skeleton } from "@noctusai/lib/design-system";
import { RetryError } from "@noctusai/lib/organ-kit";
import { api } from "@/lib/api";
import { formatCents, formatDay } from "@/lib/charges";

export type ChargeAction = "cancel" | "keep";

export interface OffboardingCharge {
  entry_id: string;
  description: string;
  due_date: string;
  amount_cents: number;
  entry_status: "open" | "partial";
  overdue: boolean;
  generation_status: string;
  external_id: string | null;
}

export interface OffboardingPreview {
  client: { id: string; name: string; active: boolean };
  charges: OffboardingCharge[];
  contracts: { id: string; title: string; status: string }[];
}

export interface ArchiveSummary {
  ok: boolean;
  cancelled: number;
  preserved: number;
  contracts_terminated: string[];
  contracts_failed: { id: string; title: string; error: string }[];
  gateway_cancelled: number;
  gateway_pending: number;
}

/** A partially paid charge cannot be cancelled: it can only be kept. */
export function defaultDecisions(charges: OffboardingCharge[]): Record<string, ChargeAction> {
  return Object.fromEntries(charges.map((c) => [c.entry_id, c.entry_status === "partial" ? "keep" : "cancel"])) as Record<string, ChargeAction>;
}

export function decisionsPayload(decisions: Record<string, ChargeAction>) {
  return { charges: Object.entries(decisions).map(([entry_id, action]) => ({ entry_id, action })) };
}

export function summaryMessage(s: Pick<ArchiveSummary, "cancelled" | "preserved" | "contracts_terminated" | "gateway_pending">): string {
  const parts = [`${s.cancelled} cobrança(s) cancelada(s)`, `${s.preserved} mantida(s)`, `${s.contracts_terminated.length} contrato(s) encerrado(s)`];
  if (s.gateway_pending > 0) parts.push(`${s.gateway_pending} cancelamento(s) no gateway pendente(s)`);
  return parts.join(" · ");
}

export function ClientOffboardingDialog({ clientId, open, onClose, onDone }: { clientId: string | null; open: boolean; onClose: () => void; onDone: () => void }) {
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  // The operator's explicit choices only; everything else is the default (cancel; keep for a partially paid charge).
  const [overrides, setOverrides] = useState<Record<string, ChargeAction>>({});
  const [submitting, setSubmitting] = useState(false);

  const preview = useQuery({
    queryKey: ["client-offboarding-preview", clientId],
    queryFn: async () => api.get<OffboardingPreview>(`/api/clients/${clientId}/offboarding-preview`),
    enabled: open && !!clientId,
    gcTime: 0,
  });

  const showSkeleton = preview.isPending && !preview.data;
  const data = preview.data;
  const decisions = useMemo(() => ({ ...defaultDecisions(data?.charges ?? []), ...overrides }), [data, overrides]);
  const setDecisions = (updater: (d: Record<string, ChargeAction>) => Record<string, ChargeAction>) => setOverrides((o) => updater({ ...o }));

  const submit = async () => {
    if (!data || !clientId) return;
    const keep = Object.values(decisions).filter((a) => a === "keep").length;
    const ok = await confirm({
      title: `Inativar ${data.client.name}?`,
      description: `${data.charges.length - keep} cobrança(s) serão canceladas, ${keep} mantida(s), e ${data.contracts.length} contrato(s) encerrado(s).`,
      confirmLabel: "Inativar cliente",
      tone: "danger",
    });
    if (!ok) return;
    setSubmitting(true);
    try {
      const res = await api.post<ArchiveSummary>(`/api/clients/${clientId}/archive`, decisionsPayload(decisions));
      toast.success("Cliente inativado", { description: summaryMessage(res) });
      queryClient.invalidateQueries({ queryKey: ["financial-charges"] });
      queryClient.invalidateQueries({ queryKey: ["financial-cash-flow"] });
      queryClient.invalidateQueries({ queryKey: ["orbity-client-options"] });
      onDone();
    } catch (err: unknown) {
      toast.error("Falha ao inativar cliente", { description: err instanceof Error ? err.message : undefined });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title="Inativar cliente" className="max-w-2xl">
      <DialogHeader><h3 className="text-base font-semibold">Inativar cliente{data ? ` — ${data.client.name}` : ""}</h3></DialogHeader>
      <DialogBody>
        {showSkeleton ? (
          <Skeleton className="h-32 w-full" />
        ) : preview.isError && !data ? (
          <RetryError message={`Erro ao carregar as cobranças do cliente: ${preview.error.message}`} onRetry={() => void preview.refetch()} retryLabel="Tentar novamente" />
        ) : data ? (
          <div className="space-y-4">
            {data.charges.length === 0 ? (
              <p className="text-sm text-muted-foreground">Este cliente não tem cobranças em aberto.</p>
            ) : (
              <div className="space-y-2">
                <p className="text-sm">
                  Escolha o que fazer com cada cobrança em aberto. <strong>Cancelar</strong> também cancela a cobrança no gateway;
                  <strong> Manter</strong> deixa a cobrança válida e ela continua entrando no fluxo de caixa.
                </p>
                <ul className="divide-y divide-border rounded-md border border-border" aria-label="Cobranças em aberto">
                  {data.charges.map((c) => (
                    <li key={c.entry_id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
                      <div>
                        <p className="font-medium">{c.description}</p>
                        <p className="text-xs text-muted-foreground">
                          Vence em {formatDay(c.due_date)} · {formatCents(c.amount_cents)}
                          {c.overdue ? <span className="ml-2 text-red-700">atrasada</span> : null}
                          {c.entry_status === "partial" ? <span className="ml-2">pago em parte</span> : null}
                          {c.external_id ? <span className="ml-2">com cobrança no gateway</span> : null}
                        </p>
                      </div>
                      <fieldset className="flex gap-3" aria-label={`Destino: ${c.description}`}>
                        <label className="flex items-center gap-1">
                          <input
                            type="radio"
                            name={`charge-${c.entry_id}`}
                            checked={decisions[c.entry_id] === "cancel"}
                            disabled={c.entry_status === "partial"}
                            onChange={() => setDecisions((d) => ({ ...d, [c.entry_id]: "cancel" }))}
                          />
                          Cancelar
                        </label>
                        <label className="flex items-center gap-1">
                          <input type="radio" name={`charge-${c.entry_id}`} checked={decisions[c.entry_id] === "keep"} onChange={() => setDecisions((d) => ({ ...d, [c.entry_id]: "keep" }))} />
                          Manter
                        </label>
                      </fieldset>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {data.contracts.length > 0 ? (
              <div className="text-sm">
                <p>Os contratos abaixo serão encerrados (sem multa):</p>
                <ul className="list-disc pl-5 text-muted-foreground">
                  {data.contracts.map((k) => <li key={k.id}>{k.title}</li>)}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button variant="outline" onClick={onClose} disabled={submitting}>Voltar</Button>
        <Button variant="destructive" onClick={() => void submit()} disabled={!data || submitting}>{submitting ? "Inativando…" : "Inativar cliente"}</Button>
      </DialogFooter>
    </Dialog>
  );
}
