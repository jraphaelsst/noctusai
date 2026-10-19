/**
 * Julia › Captação (`/julia/captacao`, wave 8). Feed of potential property
 * acquisitions the agent identified, grouped by day; expandable cards with
 * Registrar captação / Descartar; filters in the seed SideDrawer; page sizes.
 *
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useMemo, useState } from "react";
import { AlertCircle, Filter, Inbox, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useConfirm } from "@noctusai/lib";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { CaptacaoCard } from "@/components/julia/captacao/CaptacaoCard";
import { FiltroDrawer } from "@/components/julia/captacao/FiltroDrawer";
import { agruparPorDia } from "@/components/julia/captacao/agrupar";
import {
  FILTRO_VAZIO, PAGE_SIZES, useDescartarCaptacao, useJuliaCaptacoes, useRegistrarCaptacao,
  type CaptacaoFiltro, type JuliaCaptacao,
} from "@/hooks/useJuliaCaptacao";
import { mensagemErroServidor } from "@/lib/erroServidor";

export default function JuliaCaptacao() {
  const confirm = useConfirm();
  const [filtro, setFiltro] = useState<CaptacaoFiltro>(FILTRO_VAZIO);
  const [drawer, setDrawer] = useState(false);

  const q = useJuliaCaptacoes(filtro);
  const registrar = useRegistrarCaptacao();
  const descartar = useDescartarCaptacao();

  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;
  const itens = q.data?.items ?? [];
  const total = q.data?.total ?? 0;
  const grupos = useMemo(() => agruparPorDia(itens), [itens]);
  const paginas = Math.max(1, Math.ceil(total / filtro.pageSize));
  const ocupado = registrar.isPending || descartar.isPending;

  function aoRegistrar(c: JuliaCaptacao) {
    registrar.mutate(c.id, {
      onSuccess: ({ imovel_codigo }) =>
        toast.success(
          <span>
            Captação registrada.{" "}
            <Link to={`/imoveis/${encodeURIComponent(imovel_codigo)}`} className="underline">Abrir imóvel</Link>
          </span>,
        ),
      onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível registrar a captação.")),
    });
  }
  async function aoDescartar(c: JuliaCaptacao) {
    const ok = await confirm({
      title: "Descartar captação?",
      description: "A notificação será marcada como descartada.",
      confirmLabel: "Descartar",
    });
    if (!ok) return;
    descartar.mutate(c.id, {
      onSuccess: () => toast.success("Captação descartada."),
      onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível descartar a captação.")),
    });
  }

  return (
    <div className="container max-w-3xl space-y-5 py-6">
      <header className="space-y-1">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">Captação</h1>
          <div className="flex items-center gap-2">
            {isRefreshing && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="captacao-refreshing">
                <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
              </span>
            )}
            <label className="flex items-center gap-1 text-sm">
              Por página
              <select aria-label="Itens por página" className="h-8 rounded-md border bg-background px-1 text-sm"
                value={filtro.pageSize} onChange={(e) => setFiltro({ ...filtro, pageSize: Number(e.target.value), page: 1 })}>
                {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <Button variant="outline" size="sm" onClick={() => setDrawer(true)}><Filter className="mr-1 h-4 w-4" /> Filtros</Button>
          </div>
        </div>
        <p className="text-sm text-muted-foreground">Acompanhe as notificações de imóveis potencialmente captados.</p>
      </header>

      {showSkeleton ? (
        <div className="h-64 animate-pulse rounded-lg bg-muted" data-testid="captacao-skeleton" />
      ) : q.isError && !q.data ? (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="captacao-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar as captações.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>Tentar de novo</Button>
        </div>
      ) : total === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-16 text-center" data-testid="captacao-vazio">
          <Inbox className="h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Nenhuma captação encontrada.</p>
        </div>
      ) : (
        <>
          <p className="text-sm text-muted-foreground" data-testid="captacao-total">Exibindo {total} captações</p>
          {grupos.map((g) => (
            <section key={g.chave} className="space-y-2" data-testid="captacao-grupo">
              <h2 className="text-sm font-semibold">{g.rotulo}</h2>
              <ul className="space-y-2">
                {g.itens.map((c) => (
                  <CaptacaoCard key={c.id} captacao={c} ocupado={ocupado} onRegistrar={aoRegistrar} onDescartar={aoDescartar} />
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

      {drawer && (
        <FiltroDrawer filtro={filtro} onClose={() => setDrawer(false)}
          onAplicar={(f) => { setFiltro(f); setDrawer(false); }} />
      )}
    </div>
  );
}
