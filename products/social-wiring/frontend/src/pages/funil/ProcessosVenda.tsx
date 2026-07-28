/**
 * Processos de Venda — post-acceptance delivery at `/processos-venda`.
 *
 * Cards arrive here only through the Funil's "Aceitar Proposta" seam; there is
 * no create button, because a processo without the deal it came from has no
 * provenance.
 *
 * Stages are DB rows the user edits ("Configurar etapas"). The defaults
 * (Contrato → Onboarding → Briefing → Planejamento → Execução → Entrega →
 * Faturamento) are a first pass and are expected to be refined in the UI.
 */
import { useState } from "react";
import { Search } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { PipelineBoard } from "@noctusai/lib/components";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatValor } from "./formatValor";
import { processosPipeline } from "@/lib/pipelines";
import { ProcessoCard } from "./components/ProcessoCard";

function useArquivarProcesso() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (processoId: string) => {
      const result: any = await api.post(`/api/processos-venda/${processoId}/arquivar`);
      return result?.data ?? result;
    },
    onSuccess: (processo: any) => {
      toast.success(processo?.arquivado ? "Processo arquivado" : "Processo restaurado");
    },
    onError: (error: Error) =>
      toast.error("Erro ao arquivar processo", { description: error.message }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["sw-processos"] }),
  });
}

export default function ProcessosVenda() {
  const [busca, setBusca] = useState("");
  const [incluirArquivados, setIncluirArquivados] = useState(false);
  const { mutate: arquivarProcesso } = useArquivarProcesso();

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <div className="mb-6">
        <h1 className="mb-1 text-2xl font-bold">Processos de Venda</h1>
        <p className="text-sm text-muted-foreground">
          Execução pós-aceite da proposta — do contrato ao faturamento.
        </p>
      </div>

      <PipelineBoard
        hooks={processosPipeline}
        filtros={{ busca: busca || undefined, incluir_arquivados: incluirArquivados }}
        formatValue={formatValor}
        emptyColumnLabel="Nenhum processo nesta etapa"
        toolbar={
          <>
            <div className="relative min-w-[240px] flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Buscar por negociação ou observações..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
              />
            </div>
            <Button
              variant={incluirArquivados ? "default" : "outline"}
              size="sm"
              onClick={() => setIncluirArquivados((v) => !v)}
            >
              {incluirArquivados ? "Ocultar arquivados" : "Mostrar arquivados"}
            </Button>
          </>
        }
        loadingState={
          <div className="flex gap-4 overflow-x-auto pb-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-96 w-80 flex-shrink-0" />
            ))}
          </div>
        }
        renderCard={(processo, { isDragging }) => (
          <ProcessoCard
            processo={processo}
            isDragging={isDragging}
            onArquivar={arquivarProcesso}
          />
        )}
      />
    </div>
  );
}
