/**
 * Julia › Painel (`/julia/painel`, wave 9): atividades, personalizações, funil
 * and charts for one month. Loading = two signals off `data`.
 */
import { useState } from "react";
import { AlertCircle, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Atividades, Personalizacoes } from "@/components/julia/painel/Atividades";
import { Funil } from "@/components/julia/painel/Funil";
import { Graficos } from "@/components/julia/painel/Graficos";
import { mesAtual, useJuliaPainel } from "@/hooks/useJuliaPainel";
import { JULIA_LABEL, JULIA_PAGES } from "@/nav/julia";

export default function JuliaPainel() {
  const [mes, setMes] = useState(mesAtual());
  const q = useJuliaPainel(mes);
  const p = q.data;
  const vazio = !!p && p.funil.topo === 0;

  return (
    <div className="container max-w-6xl space-y-6 py-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{JULIA_LABEL} · {JULIA_PAGES.painel.name}</h1>
          <p className="text-sm text-muted-foreground">Resumo do atendimento no mês.</p>
        </div>
        <div className="flex items-center gap-3">
          {q.isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="painel-refreshing">
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
          <input type="month" aria-label="Mês" value={mes} max={mesAtual()} onChange={(e) => e.target.value && setMes(e.target.value)}
            className="h-9 rounded-md border bg-background px-2 text-sm" />
          <Button variant="outline" size="sm" onClick={() => void q.refetch()}>
            <RefreshCw className="mr-1 h-4 w-4" /> Recarregar dados
          </Button>
        </div>
      </header>

      {q.showSkeleton && <div className="h-64 animate-pulse rounded-lg bg-muted" data-testid="painel-skeleton" />}
      {q.isError && !p && (
        <div role="alert" className="flex items-center gap-2 rounded-lg border border-destructive/40 p-4 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> Não foi possível carregar o painel.
        </div>
      )}
      {p && (
        <>
          <Atividades a={p.atividades} />
          <Personalizacoes />
          <section aria-labelledby="painel-dados" className="space-y-3">
            <h2 id="painel-dados" className="text-lg font-semibold">Dados gerais de atendimento</h2>
            {vazio && <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground" data-testid="painel-vazio">Nenhum lead neste mês.</p>}
            <Funil f={p.funil} />
            <Graficos p={p} />
          </section>
        </>
      )}
    </div>
  );
}
