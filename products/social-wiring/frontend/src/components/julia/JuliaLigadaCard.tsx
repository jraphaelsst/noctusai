/**
 * Julia › Agente — THE "Julia ligada/desligada nesta empresa" switch (CONTRACT §12.1), at the top of the page.
 * The switch is the per-line `agente_leads_ativo` (the routing `alimenta` flag): one row per WhatsApp line.
 * Turning off stops her immediately, including open conversations. Red banner when the platform kill is on or the
 * org mode is not `ligado`.
 */
import { useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Loader2 } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { mensagemErroJulia, type JuliaStatusAgente } from "@/hooks/useJuliaAgente";
import { useAtualizarLinha, type LinhaRoteamento } from "@/hooks/useJuliaRoteamento";

export function JuliaLigadaBanner({ status }: { status: JuliaStatusAgente | null | undefined }) {
  if (!status) return null;
  const plataforma = status.desligado_plataforma === true;
  const modoFora = !!status.modo && status.modo !== "ligado";
  if (!plataforma && !modoFora) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
      data-testid="julia-banner-desligada"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>
        {plataforma
          ? "A Julia está desligada pela plataforma."
          : `A Julia não está respondendo: o modo de operação desta empresa é "${status.modo}".`}
      </span>
    </div>
  );
}

function Linha({ linha, isAdmin }: { linha: LinhaRoteamento; isAdmin: boolean }) {
  const atualizar = useAtualizarLinha();
  const [erro, setErro] = useState<string | null>(null);
  const id = `julia-ligada-${linha.connection_id}`;

  function alternar(v: boolean) {
    setErro(null);
    atualizar.mutate(
      { connectionId: linha.connection_id, body: { alimenta: v } },
      {
        onSuccess: () => toast.success(v ? "Julia ligada" : "Julia desligada"),
        onError: (e) => setErro(mensagemErroJulia(e, "Não foi possível salvar a alteração.")),
      },
    );
  }

  return (
    <li className="space-y-1" data-testid={`julia-ligada-${linha.connection_id}`}>
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={id} className="text-sm font-medium">
          {`Esta linha atende leads com a Julia (${linha.label})`}
          <span className={`ml-2 text-xs ${linha.alimenta ? "text-success" : "text-destructive"}`}>
            {linha.alimenta ? "Ligada" : "Desligada"}
          </span>
        </label>
        <div className="flex items-center gap-2">
          {atualizar.isPending && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          <Switch
            id={id}
            checked={linha.alimenta}
            disabled={!isAdmin || atualizar.isPending}
            onCheckedChange={alternar}
          />
        </div>
      </div>
      {erro && (
        <p role="alert" className="text-sm text-destructive" data-testid="linha-erro">
          {erro}
        </p>
      )}
    </li>
  );
}

export function JuliaLigadaCard({
  linhas,
  status,
  isAdmin,
}: {
  linhas: LinhaRoteamento[];
  status: JuliaStatusAgente | null | undefined;
  isAdmin: boolean;
}) {
  return (
    <Card data-testid="julia-ligada-card">
      <CardHeader>
        <CardTitle className="text-base">Julia ligada/desligada nesta empresa</CardTitle>
        <CardDescription>
          Desligar para imediatamente: ela não responde mais ninguém, nem conversas abertas.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <JuliaLigadaBanner status={status} />
        {linhas.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="ligada-sem-linhas">
            Nenhuma linha de WhatsApp. Conecte o WhatsApp da Julia no cartão abaixo para poder ligá-la.
          </p>
        ) : (
          <ul className="space-y-3">
            {linhas.map((l) => (
              <Linha key={l.connection_id} linha={l} isAdmin={isAdmin} />
            ))}
          </ul>
        )}
        {!isAdmin && (
          <p className="text-xs text-muted-foreground">Somente owner ou admin da organização pode alterar.</p>
        )}
      </CardContent>
    </Card>
  );
}
