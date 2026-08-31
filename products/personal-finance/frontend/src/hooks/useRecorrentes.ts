import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Recorrente } from "@/types";

export function useRecorrentes(ativo?: boolean) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["recorrentes", ativo],
    queryFn: async () => {
      const params: { ativo?: boolean } = {};
      if (ativo !== undefined) params.ativo = ativo;
      const result = await api.get("/api/recorrentes", params);
      return (result.data || []) as Recorrente[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateRecorrente() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Recorrente>) => {
      const result = await api.post("/api/recorrentes", data);
      return result.data as Recorrente;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recorrentes"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Conta recorrente criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar conta recorrente", { description: error.message });
    },
  });
}

export function useUpdateRecorrente() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Recorrente> & { id: string }) => {
      const result = await api.patch(`/api/recorrentes/${id}`, data);
      return result.data as Recorrente;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recorrentes"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Conta recorrente atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar conta recorrente", { description: error.message });
    },
  });
}

export function useDeleteRecorrente() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/recorrentes/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recorrentes"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Conta recorrente excluida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir conta recorrente", { description: error.message });
    },
  });
}

export function useExecutarPendentes() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const result = await api.post("/api/recorrentes/executar");
      return result.data as { executadas: number; pendentes_processadas: number; erros: number };
    },
    onSuccess: (data) => {
      // RecorrentesService.executar_pendentes/executar_unico both call
      // `TransacoesService.criar()` — the EXACT SAME create path
      // useTransacoes.ts's mutations go through, including
      // `_atualizar_saldo_conta`, `_sincronizar_orcamento` and
      // `_invalidar_cache_mensal`. This set was missing "conta"
      // (singular), "orcamento" and "relatorios"/"patrimonio" entirely —
      // a fix-on-contact found while auditing the sibling file, not a
      // narrowing: executing a recurring bill silently left the budget
      // "gasto" total, the monthly report and net worth all stale. Kept
      // in lockstep with `invalidateAposTransacao` in useTransacoes.ts.
      queryClient.invalidateQueries({ queryKey: ["recorrentes"] });
      queryClient.invalidateQueries({ queryKey: ["transacoes"] });
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      queryClient.invalidateQueries({ queryKey: ["conta"] });
      queryClient.invalidateQueries({ queryKey: ["orcamento"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["relatorios"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio", "atual"] });
      toast.success(`${data.executadas} transacao(oes) executada(s)`);
    },
    onError: (error: Error) => {
      toast.error("Erro ao executar pendentes", { description: error.message });
    },
  });
}

export function useExecutarUnico() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const result = await api.post(`/api/recorrentes/${id}/executar`);
      return result.data;
    },
    onSuccess: () => {
      // Same fix as useExecutarPendentes above — see its comment.
      queryClient.invalidateQueries({ queryKey: ["recorrentes"] });
      queryClient.invalidateQueries({ queryKey: ["transacoes"] });
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      queryClient.invalidateQueries({ queryKey: ["conta"] });
      queryClient.invalidateQueries({ queryKey: ["orcamento"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["relatorios"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio", "atual"] });
      toast.success("Transacao executada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao executar recorrente", { description: error.message });
    },
  });
}
