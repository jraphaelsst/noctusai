/**
 * Julia › Relatórios (`/julia/relatorios`, wave 10). Operação + month filters,
 * tabs Imóveis · Bairros. Loading = two signals off `data` (never `isLoading`).
 */
import { useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { BairrosTab } from "@/components/julia/relatorios/BairrosTab";
import { ImoveisTab } from "@/components/julia/relatorios/ImoveisTab";
import {
  mesAtual, useRelatorioBairros, useRelatorioImoveis, type RelAba, type RelOperacao,
} from "@/hooks/useJuliaRelatorios";

const SELECT = "h-9 rounded-md border bg-background px-2 text-sm";

export default function JuliaRelatorios() {
  const [operacao, setOperacao] = useState<RelOperacao>("aluguel");
  const [mes, setMes] = useState(mesAtual());
  const [aba, setAba] = useState<RelAba>("imoveis");
  const [bairro, setBairro] = useState("");

  const imoveis = useRelatorioImoveis(operacao, mes, aba === "imoveis");
  const bairros = useRelatorioBairros(operacao, mes, bairro || undefined, aba === "bairros");
  const q = aba === "imoveis" ? imoveis : bairros;

  return (
    <div className="container max-w-5xl space-y-6 py-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Relatório</h1>
          <p className="text-sm text-muted-foreground">
            Confira dados sobre as preferências dos seus leads e otimize suas campanhas e captações.
          </p>
        </div>
        {q.isRefreshing && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="rel-refreshing">
            <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
          </span>
        )}
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <select aria-label="Operação" className={SELECT} value={operacao}
          onChange={(e) => { setOperacao(e.target.value as RelOperacao); setBairro(""); }}>
          <option value="aluguel">Aluguel</option>
          <option value="compra">Compra</option>
        </select>
        <input aria-label="Mês" type="month" className={SELECT} value={mes}
          onChange={(e) => { if (e.target.value) { setMes(e.target.value); setBairro(""); } }} />
        <div role="tablist" className="ml-auto flex gap-1">
          {(["imoveis", "bairros"] as const).map((t) => (
            <Button key={t} role="tab" aria-selected={aba === t} size="sm"
              variant={aba === t ? "default" : "outline"} onClick={() => setAba(t)}>
              {t === "imoveis" ? "Imóveis" : "Bairros"}
            </Button>
          ))}
        </div>
      </div>

      {q.showSkeleton ? (
        <div className="h-64 animate-pulse rounded-lg bg-muted" data-testid="rel-skeleton" />
      ) : q.isError && !q.data ? (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="rel-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar o relatório.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>Tentar de novo</Button>
        </div>
      ) : aba === "imoveis" && imoveis.data ? (
        <ImoveisTab data={imoveis.data} operacao={operacao} />
      ) : aba === "bairros" && bairros.data ? (
        <BairrosTab data={bairros.data} operacao={operacao} bairro={bairro} onBairro={setBairro} />
      ) : null}
    </div>
  );
}
