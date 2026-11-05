/**
 * Integrações > Vista CRM (owner 2026-11-03: "keys live in the DB, not .env"): this org's own Vista credential.
 *
 *   GET    /api/integracoes/vista          → {data:{configurado, base_url, chave_final, verificado_em}}
 *   PUT    /api/integracoes/vista {base_url, api_key}   (live-checked server-side, then stored)
 *   POST   /api/integracoes/vista/testar   → {data:{ok, mensagem}}
 *   DELETE /api/integracoes/vista
 *
 * The key is WRITE-ONLY: no response carries it, so nothing here can show or cache it. Org admins only on the
 * backend (403 for a member) — callers render the card only for owner/admin. Loading = two signals off `data`
 * (`showSkeleton` first load only, `isRefreshing` for a refetch over data on screen), never `isLoading`.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";

export interface VistaIntegracao {
  configurado: boolean;
  base_url: string | null;
  /** Last 4 characters of the key — the only fragment ever shown. */
  chave_final: string | null;
  verificado_em: string | null;
}

export interface VistaSalvar {
  base_url: string;
  api_key: string;
}

export interface VistaTeste {
  ok: boolean;
  mensagem: string;
}

export const VISTA_KEY = ["sw", "integracoes", "vista"] as const;
const URL = "/api/integracoes/vista";

export function useVistaIntegracao(enabled = true) {
  const query = useQuery({
    queryKey: VISTA_KEY,
    queryFn: async () => (await api.get<{ data: VistaIntegracao }>(URL)).data,
    enabled,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useSalvarVista() {
  return useCacheWriteMutation<VistaIntegracao, VistaSalvar>({
    mutationFn: async (corpo) => (await api.put<{ data: VistaIntegracao }>(URL, corpo)).data,
    targets: [{ queryKey: VISTA_KEY, commit: (_old: VistaIntegracao | undefined, saved) => saved }],
    onSuccess: (data) => {
      toast.success(`Vista conectado (chave …${data.chave_final ?? ""}).`);
    },
    onError: (err: any) => {
      toast.error(err?.message ?? "Falha ao salvar a chave do Vista.");
    },
  });
}

export function useRemoverVista() {
  return useCacheWriteMutation<VistaIntegracao, void>({
    mutationFn: async () => (await api.delete<{ data: VistaIntegracao }>(URL)).data,
    targets: [{ queryKey: VISTA_KEY, commit: (_old: VistaIntegracao | undefined, saved) => saved }],
    onSuccess: () => {
      toast.success("Conexão com o Vista removida.");
    },
    onError: (err: any) => {
      toast.error(err?.message ?? "Falha ao remover a conexão com o Vista.");
    },
  });
}

/** A probe of the STORED credential: writes and caches nothing; the result renders inline. */
export function useTestarVista() {
  return useMutation<VistaTeste, unknown, void>({ // noc-allow: invalidate-only — a probe (writes and caches nothing)
    mutationFn: async () => (await api.post<{ data: VistaTeste }>(`${URL}/testar`, {})).data,
    onError: (err: any) => {
      toast.error("Teste falhou", { description: err?.message ?? "Erro desconhecido." });
    },
  });
}
