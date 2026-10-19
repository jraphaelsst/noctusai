/** Julia privacy notice — public read + the admin editor (contract 11.2). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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

// ─── Admin editor (GET/PUT /api/julia/agente/aviso) ───────────────────────────

export interface JuliaAvisoAdmin extends JuliaAvisoPublico {
  slug: string;
  mensagem_inicial: string;
  /** True while the notice still shows "a definir" placeholders. */
  incompleto: boolean;
}

export interface JuliaAvisoInput {
  titulo: string;
  empresa_nome: string;
  contato_email: string | null;
  contato_whatsapp: string | null;
  secoes: JuliaAvisoSecao[];
  mensagem_inicial: string;
}

const AVISO_KEY = ["sw", "julia", "aviso"] as const;

export function useJuliaAviso() {
  return useQuery({
    queryKey: AVISO_KEY,
    queryFn: async () => (await api.get<{ data: JuliaAvisoAdmin }>("/api/julia/agente/aviso")).data,
  });
}

export function useSalvarJuliaAviso() {
  const qc = useQueryClient();
  return useMutation<JuliaAvisoAdmin, unknown, JuliaAvisoInput>({
    mutationFn: async (body) => (await api.put<{ data: JuliaAvisoAdmin }>("/api/julia/agente/aviso", body)).data,
    onSuccess: (row) => {
      qc.setQueryData(AVISO_KEY, row);
      // The Agente page's "aviso_incompleto" gate reads the notice server-side.
      qc.invalidateQueries({ queryKey: ["sw", "julia", "agente"] });
    },
  });
}
