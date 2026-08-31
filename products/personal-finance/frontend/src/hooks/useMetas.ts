import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Meta } from "@/types";

export function useMetas(status?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["metas", status],
    queryFn: async () => {
      const params: { status?: string } = {};
      if (status) params.status = status;
      const result = await api.get("/api/metas", params);
      return (result.data || []) as Meta[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useMeta(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["meta", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/metas/${id}`);
      return result.data as Meta;
    },
    enabled: !!user && !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useMetaProgresso(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["meta", id, "progresso"],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/metas/${id}/progresso`);
      return result.data;
    },
    enabled: !!user && !!id,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateMeta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Meta>) => {
      const result = await api.post("/api/metas", data);
      return result.data as Meta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Meta criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar meta", { description: error.message });
    },
  });
}

export function useUpdateMeta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Meta> & { id: string }) => {
      const result = await api.patch(`/api/metas/${id}`, data);
      return result.data as Meta;
    },
    onSuccess: (meta) => {
      // Direct patch — MetaDetalhes.tsx reads `useMeta(id)` on the SAME
      // page this mutation is called from (it also calls useUpdateMeta),
      // but the "meta" singular key was never invalidated here before —
      // only "meta_contribuicoes"-driven useAddContribuicao below did
      // that. An edit on the goal's own detail page left the page not
      // reflecting its own edit.
      queryClient.setQueryData(["meta", meta.id], meta);
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      // DashboardService.resumo() returns metas_ativas (top-5 active
      // goals) — a rename/target change is visible there.
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Meta atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar meta", { description: error.message });
    },
  });
}

export function useDeleteMeta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/metas/${id}`);
    },
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      // Purge — the goal is gone; MetaDetalhes.tsx navigates away on its
      // own delete, but a refetch of `["meta", id]` from elsewhere would
      // just 404.
      queryClient.removeQueries({ queryKey: ["meta", id] });
      toast.success("Meta excluida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir meta", { description: error.message });
    },
  });
}

export function useAddContribuicao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: { id: string; valor: number; descricao?: string }) => {
      const result = await api.post(`/api/metas/${id}/contribuicao`, data);
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      queryClient.invalidateQueries({ queryKey: ["meta"] });
      // "contas" dropped — MetasService.adicionar_contribuicao only
      // inserts a `meta_contribuicoes` row and patches `metas.valor_atual`
      // server-side; it never calls `_atualizar_saldo_conta` or writes
      // to the `contas` table (`ContribuicaoCreate.transacao_id` is an
      // optional back-reference to an ALREADY-existing transação, not a
      // new one this endpoint creates). A contribution cannot move an
      // account balance through this code path.
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Contribuicao adicionada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao adicionar contribuicao", { description: error.message });
    },
  });
}
