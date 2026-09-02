/**
 * Certidões Negativas — query/mutation hooks.
 *
 * Ported verbatim (shapes AND polling contract) from
 * `erp-imobiliario/frontend/src/hooks/useCertidoes.ts` as ERP is retired.
 * Wraps `/api/certidoes/*` on the social-wiring backend.
 *
 * The polling here IS the feature, not a nicety: a consulta fans out into ~8
 * tribunal scrapes that finish minutes apart, and the page is the only place
 * the user can see which ones landed. Three independent intervals, each of
 * which returns `false` the moment there is nothing live to watch:
 *
 *   - consultas list  → 3s while ANY consulta is pendente/processando
 *   - consulta detail → 3s while THAT consulta is pendente/processando
 *   - TJSP queue      → 15s while the queue is non-empty or cooldown is active
 *
 * `useCertidaoConsultas` carries `placeholderData: (prev) => prev` because its
 * key includes the search/status filters: without it, every keystroke in the
 * search box drops `data` to undefined and unmounts the whole list. The page
 * pairs that with `isPending && !data` for the skeleton (never `isLoading`,
 * never a bare `isFetching`) — see KB § PATTERNS/frontend/lying-loading-state.md.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useAuthStore } from "@noctusai/seed/infra";

import { api } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * `na_fila` is NOT a synonym for `pendente`: TJSP rate-limits to one request
 * per 30 minutes, so a certificate can sit in an explicit queue with a visible
 * position. Collapsing it into `pendente` is what makes the page look stuck.
 */
export type CertidaoResultadoStatus = "pendente" | "processando" | "na_fila" | "sucesso" | "erro";

export interface CertidaoResultado {
  id: string;
  consulta_id: string;
  tipo: string;
  nome_display: string;
  ordem: number;
  status: CertidaoResultadoStatus;
  analise_ia?: string;
  arquivo_url?: string;
  arquivo_nome?: string;
  erro_mensagem?: string;
  created_at: string;
}

export interface TjspFilaItem {
  id: string;
  consulta_id: string;
  posicao: number;
  nome: string;
  documento: string;
  tipo_documento: string;
  created_at: string;
}

export interface TjspFilaStatus {
  items: TjspFilaItem[];
  total_na_fila: number;
  cooldown: {
    ativo: boolean;
    ultimo_request_at?: string;
    segundos_restantes?: number;
  };
}

export interface CertidaoConsulta {
  id: string;
  tipo_documento: "cpf" | "cnpj";
  documento: string;
  nome: string;
  data_nascimento?: string;
  genero?: string;
  rg?: string;
  nome_mae?: string;
  nome_pai?: string;
  status: "pendente" | "processando" | "concluida" | "erro";
  total_certidoes: number;
  concluidas: number;
  erros: number;
  created_at: string;
  resultados?: CertidaoResultado[];
}

export interface ConsultaCreateData {
  tipo_documento: "cpf" | "cnpj";
  documento: string;
  nome: string;
  data_nascimento?: string;
  genero?: string;
  rg?: string;
  nome_mae?: string;
  nome_pai?: string;
}

export interface FiltrosConsultas {
  busca?: string;
  status?: string;
}

// ─── Queries ─────────────────────────────────────────────────────────────────

export function useCertidaoConsultas(filtros?: FiltrosConsultas) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["certidao-consultas", filtros],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (filtros?.busca) params.busca = filtros.busca;
      if (filtros?.status && filtros.status !== "todos") params.status = filtros.status;
      const result = await api.get("/api/certidoes/consultas", params);
      return (result.data || []) as CertidaoConsulta[];
    },
    enabled: !!user,
    staleTime: 30 * 1000, // 30s — data changes during processing
    refetchInterval: (query) => {
      const data = query.state.data as CertidaoConsulta[] | undefined;
      if (data?.some((c) => c.status === "pendente" || c.status === "processando")) {
        return 3000; // Poll every 3s for real-time progress updates
      }
      return false;
    },
    // Key includes the filters — without this, typing in the search box
    // unmounts the table between keystrokes.
    placeholderData: (prev) => prev,
  });
}

export function useCertidaoConsulta(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["certidao-consulta", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/certidoes/consultas/${id}`);
      return result.data as CertidaoConsulta;
    },
    enabled: !!user && !!id,
    staleTime: 5 * 1000, // 5s — poll frequently during processing
    refetchInterval: (query) => {
      const data = query.state.data as CertidaoConsulta | null | undefined;
      if (data && (data.status === "pendente" || data.status === "processando")) {
        return 3000; // Poll every 3s for real-time progress updates
      }
      return false;
    },
  });
}

export function useTjspFila() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["tjsp-fila"],
    queryFn: async () => {
      const result = await api.get("/api/certidoes/fila-tjsp");
      return result.data as TjspFilaStatus;
    },
    enabled: !!user,
    staleTime: 10 * 1000,
    refetchInterval: (query) => {
      const data = query.state.data as TjspFilaStatus | undefined;
      if (data && (data.total_na_fila > 0 || data.cooldown.ativo)) {
        return 15000; // Poll every 15s while queue is active
      }
      return false;
    },
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useCreateConsulta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ConsultaCreateData) => {
      const result = await api.post("/api/certidoes/consultas", data);
      return result.data as CertidaoConsulta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["certidao-consultas"] });
      toast.success("Consulta de certidões iniciada!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar consulta", { description: error.message });
    },
  });
}

export function useReprocessarConsulta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/api/certidoes/consultas/${id}/reprocessar`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["certidao-consultas"] });
      queryClient.invalidateQueries({ queryKey: ["certidao-consulta"] });
      toast.success("Reprocessamento iniciado!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao reprocessar", { description: error.message });
    },
  });
}

export function useDeleteConsulta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/certidoes/consultas/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["certidao-consultas"] });
      toast.success("Consulta excluída com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir consulta", { description: error.message });
    },
  });
}

export function useCancelarProcessamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (consultaId: string) => {
      const result = await api.post(`/api/certidoes/consultas/${consultaId}/cancelar`);
      return result.data as { cancelados: number };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["certidao-consultas"] });
      queryClient.invalidateQueries({ queryKey: ["certidao-consulta"] });
      queryClient.invalidateQueries({ queryKey: ["tjsp-fila"] });
      toast.success(`${data.cancelados} certidão(ões) cancelada(s)`);
    },
    onError: (error: Error) => {
      toast.error("Erro ao cancelar processamento", { description: error.message });
    },
  });
}
