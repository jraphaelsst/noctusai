/**
 * useSellout — React Query hooks for sellout report submission + listing.
 *
 * Phase 7 PROPER: wired to Engineer D's three submission endpoints —
 * estruturado (/api/sellout/submit), nfe_xml (/api/sellout/upload-nfe),
 * freeform (/api/sellout/upload-attachment). The list endpoint scopes
 * to the distributor automatically (RLS in 001).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from "@noctusai/seed/infra";
import { toast } from "sonner";
import type { SelloutReport } from "@/types";

export function useSellout() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["adconnect", "sellout"],
    queryFn: async () => {
      const result = await api.get("/api/sellout/list");
      return (result.data || []) as SelloutReport[];
    },
    enabled: !!user,
    staleTime: 60 * 1000,
  });
}

// Alias used by SelloutHistory.tsx — same shape as useSellout().
export const useSelloutHistory = useSellout;

export function useSubmitSellout() {
  const queryClient = useQueryClient();

  const submitEstruturado = useMutation({
    mutationFn: async (data: {
      distributor_id: string;
      cnpj_cliente_final?: string;
      valor_total: number;
      quantidade_itens: number;
      descricao_resumida?: string;
      periodo_inicio: string;
      periodo_fim: string;
    }) => {
      const result = await api.post("/api/sellout/submit", data);
      return result.data as SelloutReport;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adconnect", "sellout"] });
      toast.success("Relatório enviado");
    },
    onError: (error: Error) => {
      toast.error("Erro ao enviar relatório", { description: error.message });
    },
  });

  const uploadNfe = useMutation({
    mutationFn: async (data: {
      distributor_id: string;
      nfe_xml: File;
      periodo_inicio: string;
      periodo_fim: string;
    }) => {
      const formData = new FormData();
      formData.append("distributor_id", data.distributor_id);
      formData.append("nfe_xml", data.nfe_xml);
      formData.append("periodo_inicio", data.periodo_inicio);
      formData.append("periodo_fim", data.periodo_fim);
      const result = await api.post("/api/sellout/upload-nfe", formData);
      return result.data as SelloutReport;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adconnect", "sellout"] });
      toast.success("NF-e enviada para análise");
    },
    onError: (error: Error) => {
      toast.error("Erro ao enviar NF-e", { description: error.message });
    },
  });

  const uploadAttachment = useMutation({
    mutationFn: async (data: {
      distributor_id: string;
      attachment: File;
      observacoes?: string;
      periodo_inicio: string;
      periodo_fim: string;
    }) => {
      const formData = new FormData();
      formData.append("distributor_id", data.distributor_id);
      formData.append("attachment", data.attachment);
      if (data.observacoes) formData.append("observacoes", data.observacoes);
      formData.append("periodo_inicio", data.periodo_inicio);
      formData.append("periodo_fim", data.periodo_fim);
      const result = await api.post("/api/sellout/upload-attachment", formData);
      return result.data as SelloutReport;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adconnect", "sellout"] });
      toast.success("Anexo enviado para análise");
    },
    onError: (error: Error) => {
      toast.error("Erro ao enviar anexo", { description: error.message });
    },
  });

  return { submitEstruturado, uploadNfe, uploadAttachment };
}

export function useReviewSellout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, status, review_notes }: { id: string; status: "aprovado" | "rejeitado"; review_notes?: string }) => {
      const result = await api.patch(`/api/sellout/${id}/review`, { status, review_notes });
      return result.data as SelloutReport;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adconnect", "sellout"] });
    },
    onError: (error: Error) => {
      toast.error("Erro ao revisar relatório", { description: error.message });
    },
  });
}
