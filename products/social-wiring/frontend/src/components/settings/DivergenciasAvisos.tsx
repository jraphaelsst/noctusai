/**
 * `<DivergenciasAvisos/>` — "Avisos de divergência" block of the Vista card. TRANSITIONAL
 * (NOC-REMEDIATE[transicao-vista-divergencias]): self-contained; delete with the divergence mechanism.
 *
 * Picker = which org member receives the WhatsApp digest of the APPROVALS a Vista sync opens (phone comes from their platform
 * profile). Nobody picked ⇒ the notice stays in the app only. The digest's on/off is the core Notificações page switch (kind
 * `vista_divergencias`), not here (owner 2026-11-15, option 1: the switchable digest is kept).
 * Each change saves at once; a refused save is shown inline (and the optimistic draw is rolled back).
 */
import { Loader2, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useUsuariosDaOrg } from "@/hooks/useJuliaEquipeWhatsapp";
import { useDivergenciasConfig, useSalvarDivergenciasConfig } from "@/hooks/useVistaDivergenciasConfig";
import { mensagemErroServidor } from "@/lib/erroServidor";

export function DivergenciasAvisos() {
  const { data, showSkeleton, isRefreshing, isError, refetch } = useDivergenciasConfig();
  const usuarios = useUsuariosDaOrg();
  const salvar = useSalvarDivergenciasConfig();

  if (showSkeleton) {
    return (
      <div className="flex items-center justify-center p-4" data-testid="divergencias-skeleton">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (isError && !data) {
    return (
      <div className="space-y-2 rounded-md border p-3 text-center" data-testid="divergencias-error">
        <p className="text-sm text-muted-foreground">Não foi possível carregar os avisos de divergência.</p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          <RotateCcw className="mr-1 h-3.5 w-3.5" />
          Tentar novamente
        </Button>
      </div>
    );
  }

  const destino = data?.destino_user_id ?? null;
  const lista = usuarios.data ?? [];
  const atual = destino ? lista.find((u) => u.id === destino) : undefined;
  const nomeAtual = atual?.nome || (destino ? "usuário que não está mais na equipe" : null);

  return (
    <section className="space-y-3 rounded-md border p-3" data-testid="divergencias-destino-bloco">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-medium">Resumo de aprovações por WhatsApp</h4>
          <p className="text-xs text-muted-foreground">
            Quando o proprietário confirma um valor diferente do Vista e uma aprovação é aberta, um resumo vai por WhatsApp
            para uma pessoa decidir. Liga e desliga em Notificações.
          </p>
        </div>
        {(isRefreshing || salvar.isPending) && (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" data-testid="divergencias-refreshing" />
        )}
      </div>

      <div className="space-y-1">
        <Label htmlFor="divergencias-destino">Quem recebe o aviso</Label>
        <select
          id="divergencias-destino"
          className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          value={destino ?? ""}
          disabled={salvar.isPending || usuarios.isPending}
          data-testid="divergencias-destino"
          onChange={(e) => salvar.mutate({ destino_user_id: e.target.value || null })}
        >
          <option value="">Ninguém (só no app)</option>
          {destino && !atual && <option value={destino}>{nomeAtual}</option>}
          {lista.map((u) => (
            <option key={u.id} value={u.id}>
              {u.nome || "Sem nome"}
            </option>
          ))}
        </select>
        {usuarios.isError && (
          <p className="text-xs text-destructive" data-testid="divergencias-usuarios-erro">
            Não foi possível carregar a lista de pessoas da empresa.
          </p>
        )}
        {!usuarios.isPending && !usuarios.isError && lista.length === 0 && (
          <p className="text-xs text-muted-foreground" data-testid="divergencias-sem-usuarios">
            Nenhuma pessoa encontrada na empresa.
          </p>
        )}
        {destino ? (
          <p className="text-xs text-muted-foreground" data-testid="divergencias-destino-atual">
            Quem recebe hoje: <strong>{nomeAtual}</strong>. O número vem do cadastro da pessoa na plataforma.
          </p>
        ) : (
          <p className="text-xs text-muted-foreground" data-testid="divergencias-sem-destino">
            Ninguém escolhido: os avisos ficam só no app.
          </p>
        )}
      </div>

      {salvar.isError && (
        <p className="text-xs font-medium text-destructive" role="alert" data-testid="divergencias-erro-salvar">
          {mensagemErroServidor(salvar.error, "Não foi possível salvar os avisos de divergência.")}
        </p>
      )}
    </section>
  );
}
