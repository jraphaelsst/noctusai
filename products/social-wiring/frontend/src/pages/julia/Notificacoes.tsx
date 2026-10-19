/**
 * Lais › Notificações (`/lais/notificacoes`, wave 6). Feed grouped by day,
 * filter drawer, mark read / all read, per-user toggle "Notificar lead pronto
 * para atendimento". `?tipo=captacao` is the Captação view (wave 8 reuses it).
 * The header bell is the seed NotificationBell (counts the same lais_* rows).
 *
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useMemo, useState } from "react";
import { AlertCircle, BellOff, CheckCheck, Filter, Loader2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { FiltroDrawer } from "@/components/lais/notificacoes/FiltroDrawer";
import { NotificacaoCard } from "@/components/lais/notificacoes/NotificacaoCard";
import { agruparPorDia } from "@/components/lais/notificacoes/agrupar";
import {
  FILTRO_VAZIO, PAGE_SIZE, useLaisNotificacoes, useMarcarLidas, usePreferenciasNotificacao,
  useSalvarPreferencias, type NotificacoesFiltro,
} from "@/hooks/useLaisNotificacoes";
import { mensagemErroServidor } from "@/lib/erroServidor";

/** The "lead pronto" toggle is the backend pseudo-tipo `lead_pronto` (it gates `novo_atendimento`). */
const TIPO_TOGGLE = "lead_pronto";

export default function LaisNotificacoes() {
  const [params, setParams] = useSearchParams();
  const [filtro, setFiltro] = useState<NotificacoesFiltro>({ ...FILTRO_VAZIO, tipo: params.get("tipo") ?? "" });
  const [drawer, setDrawer] = useState(false);

  const q = useLaisNotificacoes(filtro);
  const prefs = usePreferenciasNotificacao();
  const salvar = useSalvarPreferencias();
  const marcar = useMarcarLidas();

  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;
  const itens = q.data?.items ?? [];
  const total = q.data?.total ?? 0;
  const grupos = useMemo(() => agruparPorDia(itens), [itens]);
  const ligado = prefs.data?.lead_pronto ?? true;
  const paginas = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function aplicar(f: NotificacoesFiltro) {
    setFiltro(f);
    const next = new URLSearchParams(params);
    if (f.tipo) next.set("tipo", f.tipo); else next.delete("tipo");
    setParams(next, { replace: true });
    setDrawer(false);
  }
  function alternar(v: boolean) {
    salvar.mutate({ [TIPO_TOGGLE]: v }, {
      onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível salvar a preferência.")),
    });
  }
  const erroMarcar = (e: unknown) => toast.error(mensagemErroServidor(e, "Não foi possível marcar como lida."));

  return (
    <div className="container max-w-3xl space-y-5 py-6">
      <header className="space-y-1">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">Notificações</h1>
          <div className="flex items-center gap-2">
            {isRefreshing && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="notif-refreshing">
                <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
              </span>
            )}
            <Button variant="outline" size="sm" onClick={() => setDrawer(true)}><Filter className="mr-1 h-4 w-4" /> Filtrar</Button>
            <Button variant="outline" size="sm" disabled={marcar.isPending || !(q.data?.nao_lidas)}
              onClick={() => marcar.mutate({ todas: true }, { onError: erroMarcar })}>
              <CheckCheck className="mr-1 h-4 w-4" /> Marcar todas como lidas
            </Button>
          </div>
        </div>
        <p className="text-sm text-muted-foreground">Mantenha-se atualizado com as notificações personalizadas da Julia.</p>
      </header>

      <label className="flex items-center gap-3 rounded-lg border p-3 text-sm">
        <Switch checked={ligado} disabled={prefs.isPending && !prefs.data} onCheckedChange={alternar} aria-label="Notificar lead pronto para atendimento" />
        Notificar lead pronto para atendimento
      </label>

      {showSkeleton ? (
        <div className="h-64 animate-pulse rounded-lg bg-muted" data-testid="notif-skeleton" />
      ) : q.isError && !q.data ? (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="notif-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar as notificações.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>Tentar de novo</Button>
        </div>
      ) : total === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-16 text-center" data-testid="notif-vazio">
          <BellOff className="h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Nenhuma notificação encontrada.</p>
        </div>
      ) : (
        <>
          <p className="text-sm text-muted-foreground" data-testid="notif-total">Exibindo {total} notificações</p>
          {grupos.map((g) => (
            <section key={g.chave} className="space-y-2" data-testid="notif-grupo">
              <h2 className="text-sm font-semibold">{g.rotulo}</h2>
              <ul className="space-y-2">
                {g.itens.map((n) => (
                  <NotificacaoCard key={n.id} notificacao={n}
                    onLer={(id) => marcar.mutate({ ids: [id] }, { onError: erroMarcar })} />
                ))}
              </ul>
            </section>
          ))}
          {paginas > 1 && (
            <div className="flex items-center justify-center gap-3">
              <Button variant="outline" size="sm" disabled={filtro.page <= 1} onClick={() => setFiltro({ ...filtro, page: filtro.page - 1 })}>Anterior</Button>
              <span className="text-sm">{filtro.page} / {paginas}</span>
              <Button variant="outline" size="sm" disabled={filtro.page >= paginas} onClick={() => setFiltro({ ...filtro, page: filtro.page + 1 })}>Próxima</Button>
            </div>
          )}
        </>
      )}

      <FiltroDrawer aberto={drawer} filtro={filtro} onClose={() => setDrawer(false)} onAplicar={aplicar} />
    </div>
  );
}
