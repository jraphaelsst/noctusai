/**
 * Julia › Análise de crédito (`/julia/credito`, wave 13). Consent-first list of credit
 * analyses per contato with status chips; admins can reprocess and configure.
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useState } from "react";
import { AlertCircle, Inbox, Loader2, RefreshCw, Settings2 } from "lucide-react";
import { useConfirm } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { CreditoConfigDrawer } from "@/components/julia/credito/CreditoConfigDrawer";
import { CreditoStatusChip } from "@/components/julia/credito/StatusChip";
import {
  CREDITO_PAGE_SIZE, useCreditoConfig, useJuliaCredito, useReprocessarCredito, type CreditoStatus,
} from "@/hooks/useJuliaCredito";
import { mensagemErroServidor } from "@/lib/erroServidor";

const FILTROS: { value: "" | CreditoStatus; label: string }[] = [
  { value: "", label: "Todos" },
  { value: "pendente", label: "Pendentes" },
  { value: "aprovado", label: "Aprovados" },
  { value: "reprovado", label: "Reprovados" },
  { value: "erro", label: "Com erro" },
];

function fmt(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export default function JuliaCredito() {
  const confirm = useConfirm();
  const isAdmin = useIsOrgAdmin();
  const [status, setStatus] = useState<"" | CreditoStatus>("");
  const [page, setPage] = useState(1);
  const [drawer, setDrawer] = useState(false);

  const q = useJuliaCredito(status, page);
  const cfg = useCreditoConfig();
  const reprocessar = useReprocessarCredito();

  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;
  const itens = q.data?.items ?? [];
  const total = q.data?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / CREDITO_PAGE_SIZE));
  const semProvedor = !!cfg.data && cfg.data.provider == null;

  async function aoReprocessar(id: string, nome: string | null) {
    const ok = await confirm({
      title: "Reprocessar análise de crédito?",
      description: `A análise de ${nome ?? "este contato"} será consultada novamente.`,
      confirmLabel: "Reprocessar",
    });
    if (!ok) return;
    reprocessar.mutate(id, {
      onSuccess: () => toast.success("Reprocessamento solicitado."),
      onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível reprocessar.")),
    });
  }

  return (
    <div className="container max-w-3xl space-y-5 py-6">
      <header className="space-y-1">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">Análise de crédito</h1>
          <div className="flex items-center gap-2">
            {isRefreshing && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="credito-refreshing">
                <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
              </span>
            )}
            <select aria-label="Filtrar por status" className="h-8 rounded-md border bg-background px-1 text-sm"
              value={status} onChange={(e) => { setStatus(e.target.value as "" | CreditoStatus); setPage(1); }}>
              {FILTROS.map((f) => <option key={f.value || "todos"} value={f.value}>{f.label}</option>)}
            </select>
            {isAdmin && (
              <Button variant="outline" size="sm" onClick={() => setDrawer(true)}><Settings2 className="mr-1 h-4 w-4" /> Configurar</Button>
            )}
          </div>
        </div>
        <p className="text-sm text-muted-foreground" data-testid="credito-consentimento">
          A Julia só consulta o crédito com o consentimento do lead, registrado na conversa.
        </p>
      </header>

      {semProvedor && (
        <div className="rounded-md border border-warning/40 bg-warning-light p-3 text-sm text-warning-foreground" data-testid="credito-sem-provedor">
          Provedor de análise de crédito ainda não configurado.
        </div>
      )}

      {showSkeleton ? (
        <div className="h-64 animate-pulse rounded-lg bg-muted" data-testid="credito-skeleton" />
      ) : q.isError && !q.data ? (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="credito-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar as análises.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>Tentar de novo</Button>
        </div>
      ) : total === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-16 text-center" data-testid="credito-vazio">
          <Inbox className="h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Nenhuma análise de crédito encontrada.</p>
        </div>
      ) : (
        <>
          <ul className="space-y-2" data-testid="credito-lista">
            {itens.map((i) => (
              <li key={i.contato.id} className="rounded-lg border p-3 text-sm" data-testid="credito-item">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{i.contato.nome ?? "Sem nome"}</span>
                  <div className="flex items-center gap-2">
                    <CreditoStatusChip status={i.status} />
                    {isAdmin && (
                      <Button variant="ghost" size="sm" aria-label={`Reprocessar ${i.contato.nome ?? "contato"}`}
                        disabled={reprocessar.isPending} onClick={() => aoReprocessar(i.contato.id, i.contato.nome)}>
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>
                {i.resumo && <p className="mt-1 text-muted-foreground">{i.resumo}</p>}
                <p className="mt-1 text-xs text-muted-foreground">
                  Atualizado em {fmt(i.updated_at ?? i.created_at)} · Consentimento concedido na conversa
                </p>
              </li>
            ))}
          </ul>
          {paginas > 1 && (
            <div className="flex items-center justify-center gap-3">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button>
              <span className="text-sm">{page} / {paginas}</span>
              <Button variant="outline" size="sm" disabled={page >= paginas} onClick={() => setPage(page + 1)}>Próxima</Button>
            </div>
          )}
        </>
      )}

      {drawer && <CreditoConfigDrawer onClose={() => setDrawer(false)} />}
    </div>
  );
}
