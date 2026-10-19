/**
 * Lais › Visitas (`/lais/visitas`, wave 5). Empty state until a visit config is
 * active; then list + week/day calendar (no month view), filters
 * operação/status/responsável, and the visit dialog. Config drawer is opened
 * from the page; writes are owner/admin (server-enforced).
 *
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useMemo, useState } from "react";
import { AlertCircle, CalendarClock, Loader2, Settings2 } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { VisitaDialog } from "@/components/lais/visitas/VisitaDialog";
import { VisitasConfigDrawer } from "@/components/lais/visitas/VisitasConfigDrawer";
import { VisitasCalendario, STATUS_CLASSE, STATUS_LABEL } from "@/components/lais/visitas/VisitasCalendario";
import { chaveData } from "@/components/lais/visitas/calendario";
import { useVisitas, useVisitasConfig, visitasAtivas, type Visita, type VisitasView } from "@/hooks/useLaisVisitas";
import { LAIS_LABEL, LAIS_PAGES } from "@/nav/lais";

const SELECT = "h-9 rounded-md border bg-background px-2 text-sm";

export default function LaisVisitas() {
  const isAdmin = useIsOrgAdmin();
  const [view, setView] = useState<VisitasView>("semana");
  const [data, setData] = useState(() => chaveData(new Date()));
  const [drawer, setDrawer] = useState(false);
  const [aberta, setAberta] = useState<Visita | null>(null);
  const [fOp, setFOp] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [fResp, setFResp] = useState("");

  const cfg = useVisitasConfig();
  const ativas = visitasAtivas(cfg.data);
  const q = useVisitas(view, data);
  const showSkeleton = (cfg.isPending && !cfg.data) || (ativas && q.isPending && !q.data);
  const isRefreshing = (cfg.isFetching && !!cfg.data) || (q.isFetching && !!q.data);

  const responsaveis = useMemo(() => {
    const m = new Map<string, string>();
    for (const v of q.data ?? []) if (v.responsavel_user_id) m.set(v.responsavel_user_id, v.responsavel_nome ?? "Responsável");
    return [...m.entries()];
  }, [q.data]);
  const visitas = useMemo(
    () => (q.data ?? []).filter((v) =>
      (!fOp || v.operacao === fOp) && (!fStatus || v.status === fStatus) && (!fResp || v.responsavel_user_id === fResp)),
    [q.data, fOp, fStatus, fResp],
  );

  return (
    <div className="container max-w-5xl space-y-6 py-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{LAIS_LABEL} · {LAIS_PAGES.visitas.name}</h1>
          <p className="text-sm text-muted-foreground">Pedidos de visita recebidos no pré-atendimento.</p>
        </div>
        <div className="flex items-center gap-3">
          {isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="visitas-refreshing">
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
          <Button variant="outline" size="sm" onClick={() => setDrawer(true)}><Settings2 className="mr-1 h-4 w-4" /> Configurar visitas</Button>
        </div>
      </header>

      {showSkeleton ? (
        <div className="h-64 animate-pulse rounded-lg bg-muted" data-testid="visitas-skeleton" />
      ) : cfg.isError && !cfg.data ? (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="visitas-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar a configuração de visitas.</p>
          <Button variant="outline" size="sm" onClick={() => cfg.refetch()}>Tentar de novo</Button>
        </div>
      ) : !ativas ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed py-16 text-center" data-testid="visitas-vazio">
          <CalendarClock className="h-10 w-10 text-muted-foreground" />
          <h2 className="text-lg font-semibold">Ative as solicitações de visita</h2>
          <p className="max-w-md text-sm text-muted-foreground">
            Com elas, a Julia agenda visitas no pré-atendimento e cada pedido chega aqui.
          </p>
          <Button onClick={() => setDrawer(true)}>Configurar visitas</Button>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2" data-testid="visitas-filtros">
            <select aria-label="Operação" className={SELECT} value={fOp} onChange={(e) => setFOp(e.target.value)}>
              <option value="">Todas as operações</option><option value="compra">Compra</option><option value="aluguel">Aluguel</option>
            </select>
            <select aria-label="Status" className={SELECT} value={fStatus} onChange={(e) => setFStatus(e.target.value)}>
              <option value="">Todos os status</option>
              {(Object.keys(STATUS_LABEL) as Visita["status"][]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
            </select>
            <select aria-label="Responsável" className={SELECT} value={fResp} onChange={(e) => setFResp(e.target.value)}>
              <option value="">Todos os responsáveis</option>
              {responsaveis.map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}
            </select>
          </div>
          {q.isError && !q.data ? (
            <div className="flex items-center gap-3 text-sm text-muted-foreground" data-testid="visitas-lista-erro">
              <AlertCircle className="h-4 w-4 text-destructive" /> Não foi possível carregar as visitas.
              <Button variant="outline" size="sm" onClick={() => q.refetch()}>Tentar de novo</Button>
            </div>
          ) : (
            <>
              <VisitasCalendario view={view} data={data} visitas={visitas} onView={setView} onData={setData} onAbrir={setAberta} />
              <section aria-label="Lista de visitas" data-testid="visitas-lista" className="space-y-2">
                {visitas.length === 0 ? (
                  <p className="text-sm text-muted-foreground" data-testid="visitas-lista-vazia">Nenhuma visita neste período.</p>
                ) : visitas.map((v) => (
                  <button key={v.id} type="button" onClick={() => setAberta(v)}
                    className="flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm hover:bg-muted">
                    <span>{new Date(v.inicio).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })} · {v.contato_nome ?? "Lead"}{v.codigo_imovel ? ` · ${v.codigo_imovel}` : ""}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs ${STATUS_CLASSE[v.status]}`}>{STATUS_LABEL[v.status]}</span>
                  </button>
                ))}
              </section>
            </>
          )}
        </>
      )}

      {drawer && <VisitasConfigDrawer config={cfg.data} isAdmin={isAdmin} onClose={() => setDrawer(false)} />}
      <VisitaDialog visita={aberta} onClose={() => setAberta(null)} />
    </div>
  );
}
