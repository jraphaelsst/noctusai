/**
 * `<VistaSincronizacao/>` — "Sincronização com o Vista" block of the Vista card. TRANSITIONAL
 * (NOC-REMEDIATE[transicao-vista-divergencias]): self-contained; delete with the divergence mechanism.
 *
 * Owner 2026-11-04: Vista wins and every change is recorded in the imóvel's "Histórico"; in-app notices only for the sync
 * (the optional WhatsApp digest of opened approvals is `DivergenciasAvisos`, kept 2026-11-15). Two switches: keep imóveis up to date with Vista (`ativa`), and write
 * to Vista when the owner confirms via Julia (`vista_escrita_ativa`, default OFF, "em validação"). Each change saves at
 * once (optimistic draw, rolled back on refusal); a refused save is shown inline, never silent.
 */
import { Loader2, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useDivergenciasConfig, useSalvarDivergenciasConfig } from "@/hooks/useVistaDivergenciasConfig";
import { mensagemErroServidor } from "@/lib/erroServidor";

export function VistaSincronizacao() {
  const { data, showSkeleton, isRefreshing, isError, refetch } = useDivergenciasConfig();
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
        <p className="text-sm text-muted-foreground">Não foi possível carregar a sincronização com o Vista.</p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          <RotateCcw className="mr-1 h-3.5 w-3.5" />
          Tentar novamente
        </Button>
      </div>
    );
  }

  const disponivel = data?.vista_escrita_disponivel ?? null;
  const escritaBloqueada = disponivel === false;

  return (
    <section className="space-y-4 rounded-md border p-3" data-testid="divergencias-avisos">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium">Sincronização com o Vista</h4>
        {(isRefreshing || salvar.isPending) && (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" data-testid="divergencias-refreshing" />
        )}
      </div>

      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Manter imóveis atualizados com o Vista</p>
          <p className="text-xs text-muted-foreground" data-testid="sincronizacao-explicacao">
            O Vista prevalece: o que mudar lá muda aqui e cada mudança fica registrada no histórico do imóvel. Os
            administradores recebem avisos no app (sem e-mail); o resumo de aprovações por WhatsApp é opcional.
          </p>
        </div>
        <Switch
          checked={!!data?.ativa}
          disabled={salvar.isPending}
          aria-label="Manter imóveis atualizados com o Vista"
          data-testid="divergencias-toggle"
          onCheckedChange={(ativa) => salvar.mutate({ ativa })}
        />
      </div>

      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Editar no Vista quando o proprietário confirmar (via Julia)</p>
          <p className="text-xs text-muted-foreground" data-testid="escrita-dica">
            Em validação — mantenha desligado até a Julia estar em operação. Toda edição no Vista leva um motivo e deixa
            uma nota.
          </p>
          {escritaBloqueada && (
            <p className="text-xs font-medium text-destructive" data-testid="escrita-indisponivel">
              Indisponível: a chave do Vista desta empresa não tem permissão para editar imóveis. Peça ao Vista para
              liberar a escrita na chave.
            </p>
          )}
          {disponivel === null && (
            <p className="text-xs text-muted-foreground" data-testid="escrita-desconhecida">
              Não foi possível verificar se a chave do Vista permite editar imóveis.
            </p>
          )}
        </div>
        <Switch
          checked={!!data?.vista_escrita_ativa}
          disabled={salvar.isPending || escritaBloqueada}
          aria-label="Editar no Vista quando o proprietário confirmar (via Julia)"
          data-testid="escrita-toggle"
          onCheckedChange={(vista_escrita_ativa) => salvar.mutate({ vista_escrita_ativa })}
        />
      </div>

      {salvar.isError && (
        <p className="text-xs font-medium text-destructive" role="alert" data-testid="divergencias-erro-salvar">
          {mensagemErroServidor(salvar.error, "Não foi possível salvar a sincronização com o Vista.")}
        </p>
      )}
    </section>
  );
}
