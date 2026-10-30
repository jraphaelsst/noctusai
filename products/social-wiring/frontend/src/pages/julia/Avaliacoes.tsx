/**
 * Julia › Avaliações no Google (`/julia/avaliacoes`, wave 13). Monthly KPIs, star
 * distribution, latest reviews; not-configured states; admin config drawer.
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useState } from "react";
import { AlertCircle, ExternalLink, Loader2, Settings2, Star } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { AvaliacoesConfigDrawer } from "@/components/julia/avaliacoes/ConfigDrawer";
import { Distribuicao } from "@/components/julia/avaliacoes/Distribuicao";
import { mesAtual, useJuliaAvaliacoes } from "@/hooks/useJuliaAvaliacoes";

const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

export function nomeMes(mes: string): string {
  const n = Number(mes.split("-")[1]);
  return MESES[n - 1] ?? mes;
}
function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
}

export default function JuliaAvaliacoes() {
  const isAdmin = useIsOrgAdmin();
  const [mes, setMes] = useState(mesAtual());
  const [drawer, setDrawer] = useState(false);
  const q = useJuliaAvaliacoes(mes);

  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;
  const d = q.data;

  return (
    <div className="container max-w-3xl space-y-5 py-6">
      <header className="space-y-1">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">Avaliações no Google</h1>
          <div className="flex items-center gap-2">
            {isRefreshing && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="avaliacoes-refreshing">
                <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
              </span>
            )}
            <input type="month" aria-label="Mês" className="h-8 rounded-md border bg-background px-2 text-sm"
              value={mes} onChange={(e) => e.target.value && setMes(e.target.value)} />
            {isAdmin && (
              <Button variant="outline" size="sm" onClick={() => setDrawer(true)}><Settings2 className="mr-1 h-4 w-4" /> Configurar</Button>
            )}
          </div>
        </div>
      </header>

      {showSkeleton ? (
        <div className="h-64 animate-pulse rounded-lg bg-muted" data-testid="avaliacoes-skeleton" />
      ) : q.isError && !d ? (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="avaliacoes-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar as avaliações.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>Tentar de novo</Button>
        </div>
      ) : d ? (
        <>
          <section className="rounded-lg border p-4" data-testid="avaliacoes-headline">
            <h2 className="font-semibold">A Julia está construindo sua reputação</h2>
            <p className="text-sm text-muted-foreground">
              Em {nomeMes(mes)}, a Julia enviou {d.pedidos_enviados} pedidos de avaliação para leads com boas conversas.
            </p>
          </section>

          {!d.configurado.review_url && (
            <div className="rounded-md border border-warning/40 bg-warning-light p-3 text-sm text-warning-foreground" data-testid="avaliacoes-sem-link">
              Cadastre o link de avaliação do Google
              {isAdmin && <> — <button type="button" className="underline" onClick={() => setDrawer(true)}>configurar agora</button></>}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border p-4"><p className="text-xs text-muted-foreground">Pedidos enviados</p>
              <p className="text-2xl font-bold" data-testid="kpi-pedidos">{d.pedidos_enviados}</p></div>
            <div className="rounded-lg border p-4"><p className="text-xs text-muted-foreground">Novas avaliações</p>
              <p className="text-2xl font-bold" data-testid="kpi-novas">{d.novas_avaliacoes}</p></div>
          </div>

          {!d.configurado.gbp ? (
            <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground" data-testid="avaliacoes-sem-gbp">
              Conecte o Google Business Profile para ver as avaliações recebidas
            </div>
          ) : (
            <>
              <section className="space-y-3 rounded-lg border p-4">
                <div className="flex items-center gap-2">
                  <Star className="h-5 w-5 fill-warning text-warning-foreground" />
                  <span className="text-xl font-bold" data-testid="avaliacoes-media">{d.media != null ? d.media.toFixed(1) : "—"}</span>
                  <span className="text-sm text-muted-foreground" data-testid="avaliacoes-total">{d.total} avaliações</span>
                </div>
                <Distribuicao distribuicao={d.distribuicao} total={d.total} />
              </section>
              <section className="space-y-2">
                <h2 className="text-sm font-semibold">Últimas avaliações</h2>
                {d.ultimas.length === 0 ? (
                  <p className="text-sm text-muted-foreground" data-testid="avaliacoes-vazio">Nenhuma avaliação recebida ainda.</p>
                ) : (
                  <ul className="space-y-2" data-testid="avaliacoes-ultimas">
                    {d.ultimas.map((a, i) => (
                      <li key={i} className="rounded-lg border p-3 text-sm">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium">{a.autor ?? "Anônimo"} · {a.nota}★</span>
                          <span className="flex items-center gap-2 text-xs text-muted-foreground">
                            {fmt(a.data)}
                            {a.link && <a href={a.link} target="_blank" rel="noopener noreferrer" aria-label="Abrir avaliação no Google"><ExternalLink className="h-4 w-4" /></a>}
                          </span>
                        </div>
                        {a.texto && <p className="mt-1 text-muted-foreground">{a.texto}</p>}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}
        </>
      ) : null}

      {drawer && <AvaliacoesConfigDrawer onClose={() => setDrawer(false)} />}
    </div>
  );
}
