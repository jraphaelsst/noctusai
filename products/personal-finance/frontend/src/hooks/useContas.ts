import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Conta } from "@/types";

export function useContas(ativo?: boolean) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["contas", ativo],
    queryFn: async () => {
      const params: { ativo?: boolean } = {};
      if (ativo !== undefined) params.ativo = ativo;
      const result = await api.get("/api/contas", params);
      return (result.data || []) as Conta[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useConta(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["conta", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/contas/${id}`);
      return result.data as Conta;
    },
    enabled: !!user && !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useSaldos() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["contas", "saldos"],
    queryFn: async () => {
      const result = await api.get("/api/contas/saldos");
      return result.data;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateConta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Conta>) => {
      const result = await api.post("/api/contas", data);
      return result.data as Conta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      // Adding an account changes contas.saldo → PatrimonioService/
      // DashboardService.kpis both read it live. Keep both.
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      // Narrowed to "atual" — calcular_atual() reads live contas.saldo;
      // "historico" is immutable snapshot rows, only useCriarSnapshot
      // (usePatrimonio.ts) writes them.
      queryClient.invalidateQueries({ queryKey: ["patrimonio", "atual"] });
      toast.success("Conta criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar conta", { description: error.message });
    },
  });
}

export function useUpdateConta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Conta> & { id: string }) => {
      const result = await api.patch(`/api/contas/${id}`, data);
      return result.data as Conta;
    },
    onSuccess: (conta) => {
      // Direct patch, not invalidate — the response already carries the
      // full updated row. This was missing before: ContaDetalhes.tsx
      // reads `useConta(id)` on the SAME page this mutation is called
      // from, so editing an account there left its own header (name,
      // balance) showing the pre-edit value until an unrelated refetch
      // happened to land — a page not reflecting its own edit.
      queryClient.setQueryData(["conta", conta.id], conta);
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio", "atual"] });
      toast.success("Conta atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar conta", { description: error.message });
    },
  });
}

export function useDeleteConta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/contas/${id}`);
    },
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["contas"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["patrimonio", "atual"] });
      // Purge rather than invalidate — the account is gone, so
      // refetching `["conta", id]` would just 404. removeQueries drops
      // it from cache instead of triggering a doomed refetch.
      queryClient.removeQueries({ queryKey: ["conta", id] });
      toast.success("Conta excluída com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir conta", { description: error.message });
    },
  });
}
