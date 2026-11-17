/** Julia privacy notice — public read + the admin read (contract 11.2). Read for any org member; the PUT is platform-admin only (the server enforces). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMeAccess } from "@noctusai/lib/design-system";

import { api } from "@/lib/api";

export interface JuliaAvisoSecao {
  n: string;
  title: string;
  blocks: ({ p: string } | { ul: string[] })[];
}

export interface JuliaAvisoPublico {
  titulo: string | null;
  empresa_nome: string | null;
  contato_email: string | null;
  contato_whatsapp: string | null;
  secoes: JuliaAvisoSecao[];
  versao: number;
  atualizado_em: string | null;
}

export function useJuliaAvisoPublico(slug: string | undefined) {
  return useQuery({
    queryKey: ["sw", "julia", "aviso-publico", slug ?? "_none"],
    enabled: !!slug,
    retry: false,
    // 404 is a stable state the page renders itself ("Aviso não encontrado").
    meta: { suppressErrorToastStatuses: [404] },
    queryFn: () =>
      api.get<{ data: JuliaAvisoPublico }>(`/api/public/julia/privacidade/${encodeURIComponent(slug!)}`),
  });
}

// ─── Admin read (GET /api/julia/agente/aviso) + platform-admin save (PUT, same path) ───────────────────────────

export interface JuliaAvisoAdmin extends JuliaAvisoPublico {
  slug: string;
  mensagem_inicial: string;
  /** True while the notice still shows "a definir" placeholders. */
  incompleto: boolean;
}

const AVISO_KEY = ["sw", "julia", "aviso"] as const;

export function useJuliaAviso() {
  return useQuery({
    queryKey: AVISO_KEY,
    queryFn: async () => (await api.get<{ data: JuliaAvisoAdmin }>("/api/julia/agente/aviso")).data,
  });
}

export interface JuliaAvisoInput {
  titulo: string;
  empresa_nome: string;
  contato_email: string | null;
  contato_whatsapp: string | null;
  mensagem_inicial: string;
  secoes: JuliaAvisoSecao[];
}

/** The PUT answer is the full saved notice (new `versao`): it replaces the cached read. */
export function useSalvarAviso() {
  const qc = useQueryClient();
  return useMutation<JuliaAvisoAdmin, unknown, JuliaAvisoInput>({
    mutationFn: async (body) => (await api.put<{ data: JuliaAvisoAdmin }>("/api/julia/agente/aviso", body)).data,
    onSuccess: (saved) => qc.setQueryData(AVISO_KEY, saved),
  });
}

/** UX gate only (the server enforces): NoctusAI platform staff, from `/api/me/access`. */
export function useIsPlatformAdmin(): boolean {
  const role = useMeAccess().data?.org_selection?.platform_role;
  return role === "admin" || role === "owner";
}
