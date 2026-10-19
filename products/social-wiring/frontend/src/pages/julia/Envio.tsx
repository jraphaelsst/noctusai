/** Julia › Envio (`/julia/envio`) — contract §5 W3: send rules wizard + policy cards. */
import { useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EnvioWizard } from "@/components/julia/envio/EnvioWizard";
import { PoliticasCards } from "@/components/julia/envio/PoliticasCards";
import { rotuloCriterio, garantirBase, clonarGrupos } from "@/components/julia/envio/criterios";
import { regraDe, useEnvioPoliticas, useEnvioRegras, type RegrasEnvio } from "@/hooks/useJuliaEnvio";
import { JULIA_LABEL, JULIA_PAGES } from "@/nav/julia";

function ResumoRegras({ regras }: { regras: RegrasEnvio }) {
  const ops = regras.regras.length ? regras.regras.map((r) => r.operacao) : (["ambas"] as const);
  return (
    <div className="space-y-3" data-testid="envio-regras-resumo">
      {ops.map((op) => (
        <div key={op}>
          <p className="text-xs font-semibold uppercase text-muted-foreground">
            {op === "ambas" ? "Compra e aluguel" : op === "compra" ? "Compra" : "Aluguel"}
          </p>
          <ul className="mt-1 space-y-1 text-sm">
            {garantirBase(clonarGrupos(regraDe(regras, op))).map((g, i) => (
              <li key={i}>{i > 0 && <span className="mr-1 text-xs text-muted-foreground">OU</span>}{g.map(rotuloCriterio).join(" E ")}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export default function JuliaEnvio() {
  const isAdmin = useIsOrgAdmin();
  const regras = useEnvioRegras();
  const politicas = useEnvioPoliticas();
  const [editando, setEditando] = useState(false);

  // Two signals off `data` — never `isLoading`.
  const showSkeleton = (regras.isPending && !regras.data) || (politicas.isPending && !politicas.data);
  const isRefreshing = (regras.isFetching && !!regras.data) || (politicas.isFetching && !!politicas.data);
  const erro = (regras.isError && !regras.data) || (politicas.isError && !politicas.data);

  return (
    <div className="container max-w-4xl space-y-6 py-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{JULIA_LABEL} · {JULIA_PAGES.envio.name}</h1>
          <p className="text-sm text-muted-foreground">Defina quando a Julia envia leads qualificados ao SW.</p>
        </div>
        {isRefreshing && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="envio-refreshing">
            <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
          </span>
        )}
      </header>

      {showSkeleton ? (
        <div className="space-y-3" data-testid="envio-skeleton">
          <Skeleton className="h-32 w-full" /><Skeleton className="h-40 w-full" />
        </div>
      ) : erro ? (
        <Card><CardContent className="flex items-center justify-between gap-3 py-6" data-testid="envio-erro">
          <span className="flex items-center gap-2 text-sm text-destructive"><AlertCircle className="h-4 w-4" /> Não foi possível carregar as configurações de envio.</span>
          <Button variant="outline" size="sm" onClick={() => { void regras.refetch(); void politicas.refetch(); }}>Tentar de novo</Button>
        </CardContent></Card>
      ) : (
        <>
          <Card data-testid="envio-regras">
            <CardContent className="space-y-4 py-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-semibold">Envio de leads qualificados</h2>
                  <p className="text-sm text-muted-foreground">A Julia qualifica e envia ao SW os leads que atenderem algum dos critérios.</p>
                </div>
                <Button size="sm" onClick={() => setEditando(true)} data-testid="envio-editar">
                  {isAdmin ? "Editar critérios" : "Ver critérios"}
                </Button>
              </div>
              {regras.data && <ResumoRegras regras={regras.data} />}
            </CardContent>
          </Card>
          {politicas.data && <PoliticasCards politicas={politicas.data} isAdmin={isAdmin} />}
        </>
      )}

      {editando && (
        <EnvioWizard key="wizard" regras={regras.data} isAdmin={isAdmin} onClose={() => setEditando(false)} />
      )}
    </div>
  );
}
