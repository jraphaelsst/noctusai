/**
 * `<VistaAtualizacaoLine/>` — "Última atualização do Vista" under the Imóveis header.
 *
 * Shows when the mirror last ran, WHICH path ran (Vista's listar, or the per-code refresh used while listar is silent) and the
 * counts (novos · atualizados · removidos · falhas), with an "Atualizar agora" button for org admins. The button queues the
 * refresh (202) and the line hands off to polling (`useUltimaAtualizacaoVista`, 5 s while `em_andamento`); when the run
 * finishes the imóveis list is refetched and a toast says how it ended — a degraded run is never reported as clean.
 */
import { useEffect, useRef } from "react";
import { Loader2, RefreshCw, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  useAtualizarVista,
  useInvalidarImoveis,
  useUltimaAtualizacaoVista,
  type UltimaAtualizacaoVista,
} from "@/hooks/useImoveis";

const CAMINHO: Record<string, string> = { listar: "listagem do Vista", detalhes: "imóvel a imóvel" };
const STATUS_RUIM: Record<string, string> = {
  incompleto: "terminou com falhas",
  listar_vazio: "o Vista não listou imóveis",
  removidos_excessivos: "removidos em excesso — nada foi marcado",
  falhou: "falhou",
};

function quando(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function resumo(u: UltimaAtualizacaoVista): string {
  return `${u.novos} novos · ${u.atualizados} atualizados · ${u.removidos} removidos · ${u.falhas} falhas`;
}

export default function VistaAtualizacaoLine({ podeAtualizar }: { podeAtualizar: boolean }) {
  const invalidarImoveis = useInvalidarImoveis();
  const { data, showSkeleton, isRefreshing, isError, refetch } = useUltimaAtualizacaoVista();
  const atualizar = useAtualizarVista();
  const eraAndamento = useRef(false);

  // Hand-off finished: the run that was going is over -> refetch the list and say how it ended.
  useEffect(() => {
    if (!data) return;
    if (eraAndamento.current && !data.em_andamento) {
      void invalidarImoveis();
      const ruim = data.status ? STATUS_RUIM[data.status] : undefined;
      if (ruim) toast.warning(`Atualização do Vista: ${ruim}. ${resumo(data)}`, { duration: 10000 });
      else toast.success(`Imóveis atualizados. ${resumo(data)}`);
    }
    eraAndamento.current = data.em_andamento;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  async function agora() {
    try {
      const r = await atualizar.mutateAsync({ modo: "auto" });
      if (r.ja_em_andamento) toast.info("Já existe uma atualização em andamento.");
      else toast.info("Atualização do Vista iniciada. Pode levar alguns minutos.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao iniciar a atualização do Vista.");
    }
  }

  const andamento = Boolean(data?.em_andamento) || atualizar.isPending;

  let conteudo: React.ReactNode;
  if (showSkeleton) {
    conteudo = <span data-testid="vista-linha-carregando">Carregando…</span>;
  } else if (isError && !data) {
    conteudo = (
      <span data-testid="vista-linha-erro">
        Não foi possível carregar a última atualização.{" "}
        <button type="button" className="underline" onClick={() => void refetch()}>
          Tentar de novo
        </button>
      </span>
    );
  } else if (data && data.execucao_id) {
    const ruim = data.status ? STATUS_RUIM[data.status] : undefined;
    conteudo = (
      <span data-testid="vista-linha-resumo">
        {data.em_andamento ? "Atualizando agora…" : `Última atualização do Vista: ${quando(data.finalizado_em ?? data.iniciado_em)}`}
        {data.caminho ? ` · ${CAMINHO[data.caminho] ?? data.caminho}` : ""}
        {!data.em_andamento ? ` · ${resumo(data)}` : ""}
        {ruim && (
          <span className="ml-1 inline-flex items-center gap-1 text-destructive" data-testid="vista-linha-alerta">
            <TriangleAlert className="h-3 w-3" />
            {ruim}
          </span>
        )}
      </span>
    );
  } else {
    conteudo = (
      <span data-testid="vista-linha-sem-execucao">
        Última atualização do Vista: {quando(data?.sincronizado_em ?? null)}
      </span>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground" data-testid="vista-atualizacao-linha">
      {conteudo}
      {isRefreshing && !andamento && <Loader2 className="h-3 w-3 animate-spin" data-testid="vista-linha-atualizando" />}
      {podeAtualizar && (
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={agora} disabled={andamento} data-testid="vista-atualizar-agora">
          {andamento ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
          {andamento ? "Atualizando…" : "Atualizar agora"}
        </Button>
      )}
    </div>
  );
}
