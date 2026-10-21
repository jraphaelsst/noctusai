/**
 * Julia > Equipe (staff of the org's WhatsApp lines; owner 2026-10-21: "only those registered on the sw are staff and their roles ...
 * by default, if not in the staff list, it's an incoming lead").
 *
 *   GET    /api/julia/equipe-whatsapp                → {data:{items, papeis, operadores}}
 *   GET    /api/julia/equipe-whatsapp/usuarios       → {data:[{id,nome,org_role}]}   (org users that can be linked)
 *   POST   /api/julia/equipe-whatsapp {nome,papel,telefone?,user_id?}
 *   PATCH  /api/julia/equipe-whatsapp/{id}
 *   DELETE /api/julia/equipe-whatsapp/{id}
 *
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type PapelEquipe = "admin" | "operador" | "corretor" | "atendente" | "outro";

export interface MembroEquipe {
  id: string;
  user_id: string | null;
  nome: string;
  papel: PapelEquipe;
  telefone: string | null;
  ativo: boolean;
  created_at?: string;
}
export interface EquipeLista { items: MembroEquipe[]; papeis: PapelEquipe[]; operadores: PapelEquipe[] }
export interface UsuarioOrg { id: string; nome: string | null; org_role: string | null }
export interface MembroEntrada { nome: string; papel: PapelEquipe; telefone?: string | null; user_id?: string | null }

export const ROTULO_PAPEL: Record<PapelEquipe, string> = {
  admin: "Administrador", operador: "Operador", corretor: "Corretor", atendente: "Atendente", outro: "Outro",
};
export const EXPLICACAO_PAPEL: Record<PapelEquipe, string> = {
  admin: "Pode usar o One Chat (agente operador) pelo próprio WhatsApp.",
  operador: "Pode usar o One Chat (agente operador) pelo próprio WhatsApp.",
  corretor: "Equipe: nunca é tratado como lead; a mensagem na linha pública é guardada e os admins são avisados.",
  atendente: "Equipe: nunca é tratado como lead; a mensagem na linha pública é guardada e os admins são avisados.",
  outro: "Equipe: nunca é tratado como lead; a mensagem na linha pública é guardada e os admins são avisados.",
};

export const EQUIPE_WHATSAPP_KEY = ["sw", "julia", "equipe-whatsapp"] as const;
const BASE = "/api/julia/equipe-whatsapp";

export function useEquipeWhatsapp(enabled = true) {
  const q = useQuery({
    enabled,
    queryKey: [...EQUIPE_WHATSAPP_KEY, "lista"],
    queryFn: async () => (await api.get<{ data: EquipeLista }>(BASE)).data,
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

export function useUsuariosDaOrg(enabled = true) {
  return useQuery({
    enabled,
    queryKey: [...EQUIPE_WHATSAPP_KEY, "usuarios"],
    queryFn: async () => (await api.get<{ data: UsuarioOrg[] }>(`${BASE}/usuarios`)).data,
    staleTime: 60_000,
  });
}

function useInvalidar() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: EQUIPE_WHATSAPP_KEY });
}

export function useCriarMembro() {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, MembroEntrada>({
    mutationFn: (corpo) => api.post(BASE, corpo),
    onSettled: inv,
  });
}

export function useAtualizarMembro() {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, { id: string; campos: Partial<MembroEntrada> & { ativo?: boolean } }>({
    mutationFn: ({ id, campos }) => api.patch(`${BASE}/${encodeURIComponent(id)}`, campos),
    onSettled: inv,
  });
}

export function useRemoverMembro() {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, { id: string }>({
    mutationFn: ({ id }) => api.delete(`${BASE}/${encodeURIComponent(id)}`),
    onSettled: inv,
  });
}

/** `5511977770009` -> `+55 11 97777-0009` (display only; the server stores digits). */
export function formatarTelefone(d: string | null): string {
  if (!d) return "—";
  const m = /^(\d{2})(\d{2})(\d{4,5})(\d{4})$/.exec(d);
  return m ? `+${m[1]} ${m[2]} ${m[3]}-${m[4]}` : `+${d}`;
}
